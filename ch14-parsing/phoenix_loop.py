#!/usr/bin/env python3
"""
phoenix_loop.py — 죽어도 이어가는 파싱 루프 (14장 "불사조")

    python phoenix_loop.py --papers /papers --packages /packages [--list lists/verified.csv]

/papers/<논문ID>/ 폴더마다:
    *.nxml 이 있으면        → nxml_parser 로 곧장
    *.pdf 만 있으면          → scan_check 로 스캔본 판별 → 스캔본이면 격리
                               아니면 pdf_to_nxml 로 조립한 뒤 같은 파서로 (합류)
    신원이 어긋나면          → 격리

체크포인트는 볼륨에 둔 JSON 파일 하나 (실제 parse_59k_v2.py 와 같은 모양):
    /packages/parsing_checkpoint.json = {"processed": [...], "failed": [...], "last_index": N}
    논문 한 편이 끝날 때마다 다시 쓴다. 새 배는 이 파일을 읽고 끝난 논문을 건너뛴다.
    끝난 목록에 없는데 결과 폴더가 있으면 — 죽다 남긴 반쪽이다. 비우고 처음부터.

컨테이너 안에서 돌린다 (run_parser.sh). 프로세스가 죽으면 셸 루프가 새 컨테이너를 띄우고,
새 프로세스는 이 파일의 첫 줄부터 다시 시작해 체크포인트를 보고 이어간다.

    --exit-after N   N편을 끝내면 스스로 정상 종료한다 ("죽기 전에 스스로 죽는다")
    --crash-after N  N편을 끝낸 뒤 일부러 비정상 종료한다 (실습용 — 되살아나는 것을 눈으로 보라)
"""
import argparse
import gc
import json
import os
import shutil
import sys
import time
from pathlib import Path

from nxml_parser import IdentityMismatch, parse_one

# 윈도우 콘솔에서 한글·기호가 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

CHECKPOINT_NAME = "parsing_checkpoint.json"


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def cleanup_memory() -> None:
    """논문 한 편마다 — 2장의 그 청소. GPU 가 있으면 GPU 메모리도."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except ImportError:
        pass


def load_checkpoint(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed": [], "failed": [], "last_index": 0}


def save_checkpoint(path: Path, ck: dict) -> None:
    tmp = path.with_suffix(".json.tmp")                # 쓰다 죽어도 반쪽 JSON 이 남지 않게
    tmp.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def quarantine(paper_dir: Path, qdir: Path, reason: str) -> None:
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{paper_dir.name}.txt").write_text(reason + "\n", encoding="utf-8")
    log(f"[격리] {paper_dir.name}: {reason}")


def find_nxml(paper_dir: Path, qdir: Path) -> Path | None:
    """nxml 을 돌려준다. 없으면 pdf 에서 만들어 돌려준다. 만들 수 없으면 None."""
    nxmls = sorted(paper_dir.glob("*.nxml"))
    if nxmls:
        return nxmls[0]

    pdfs = sorted(paper_dir.glob("*.pdf"))
    if not pdfs:
        quarantine(paper_dir, qdir, "nxml 도 pdf 도 없음")
        return None

    from scan_check import is_scanned
    if is_scanned(pdfs[0]):
        quarantine(paper_dir, qdir, "스캔본 — 텍스트 레이어 없음")
        return None

    meta_json = paper_dir / "meta.json"          # 10장에서 받아 둔 NCBI 서지
    if not meta_json.exists():
        quarantine(paper_dir, qdir, "pdf 뿐인데 meta.json(NCBI 서지) 이 없음")
        return None

    from pdf_to_nxml import assemble_nxml, convert_with_docling
    from lxml import etree
    meta = json.loads(meta_json.read_text(encoding="utf-8"))
    doc = convert_with_docling(pdfs[0], paper_dir)
    out = paper_dir / f"{paper_dir.name}.nxml"    # 원본과 같은 폴더, 같은 이름 규칙 → 합류
    out.write_bytes(etree.tostring(assemble_nxml(meta, doc), pretty_print=True, xml_declaration=True, encoding="UTF-8"))
    log(f"[조립] {paper_dir.name}: pdf → nxml")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", type=Path, required=True)
    ap.add_argument("--packages", type=Path, required=True)
    ap.add_argument("--list", type=Path, default=None)
    ap.add_argument("--quarantine", type=Path, default=None, help="기본: <packages>/_quarantine")
    ap.add_argument("--exit-after", type=int, default=0)
    ap.add_argument("--crash-after", type=int, default=0)
    a = ap.parse_args()
    qdir = a.quarantine or (a.packages / "_quarantine")
    a.packages.mkdir(parents=True, exist_ok=True)
    ck_path = a.packages / CHECKPOINT_NAME

    paper_dirs = sorted(d for d in a.papers.iterdir() if d.is_dir())
    ck = load_checkpoint(ck_path)
    done = set(ck["processed"])
    failed = {f["pmcid"] for f in ck["failed"]}
    log(f"새 배가 뜬다 — 논문 폴더 {len(paper_dirs)}개")
    log(f"체크포인트: 끝난 논문 {len(done)}편은 건너뛴다 · 실패 {len(failed)}편")

    finished = 0
    for i, paper_dir in enumerate(paper_dirs):
        pid = paper_dir.name
        if pid in done or pid in failed:
            continue                                        # 이미 끝났거나 격리된 논문
        out = a.packages / pid
        if out.exists():
            log(f"[반쪽] {pid}: 죽다 남긴 결과를 비우고 다시")
            shutil.rmtree(out)

        nxml = find_nxml(paper_dir, qdir)
        if nxml is None:
            ck["failed"].append({"pmcid": pid, "error": "quarantined"})
            save_checkpoint(ck_path, ck)
            continue
        try:
            r = parse_one(nxml, out, a.list)
        except IdentityMismatch as e:
            shutil.rmtree(out, ignore_errors=True)
            quarantine(paper_dir, qdir, str(e))
            ck["failed"].append({"pmcid": pid, "error": str(e)})
            save_checkpoint(ck_path, ck)
            continue

        finished += 1
        if a.crash_after and finished >= a.crash_after:
            log(f"[실습] {pid} 저장 직후, 체크포인트에 올리기 전에 일부러 쓰러진다 (Signal 11 흉내)")
            os._exit(11)                                    # 끝난 목록에 없으니 다음 배가 다시 한다

        ck["processed"].append(pid)                         # 끝났다는 기록 — 볼륨에 남는다
        ck["last_index"] = i
        save_checkpoint(ck_path, ck)
        cleanup_memory()
        log(f"[완료] {pid}: 문단 {r['paragraphs']} · 그림 {r['figures']} · 표 {r['tables']}")

        if a.exit_after and finished >= a.exit_after:
            log(f"{finished}편 처리. 메모리가 눌러붙기 전에 스스로 내려간다 — 루프가 다시 띄운다")
            return 0

    log(f"전부 끝났다. 이번 배에서 {finished}편 · 누적 {len(ck['processed'])}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
