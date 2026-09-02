#!/usr/bin/env python3
"""
phoenix_loop.py — 죽어도 이어가는 파싱 루프 (14장 "불사조")

    python phoenix_loop.py --papers /papers --packages /packages [--list lists/verified.csv]

/papers/<논문ID>/ 폴더마다:
    *.nxml 이 있으면        → nxml_parser 로 곧장
    *.pdf 만 있으면          → scan_check 로 스캔본 판별 → 스캔본이면 격리
                               아니면 pdf_to_nxml 로 조립한 뒤 같은 파서로 (합류)
    신원이 어긋나면          → 격리

체크포인트는 논문 단위:
    /packages/<논문ID>/_DONE 가 있으면 건너뛴다
    _DONE 없이 파일이 남아 있으면 죽다 남긴 반쪽 — 비우고 처음부터

컨테이너 안에서 돌린다. 프로세스가 죽으면 도커가 다시 띄우고(run_parser.sh),
새 프로세스는 이 파일의 첫 줄부터 다시 시작해 _DONE 을 보고 이어간다.

    --exit-after N   N편을 끝내면 스스로 정상 종료한다 ("죽기 전에 스스로 죽는다")
    --crash-after N  N편을 끝낸 뒤 일부러 비정상 종료한다 (실습용 — 되살아나는 것을 눈으로 보라)
"""
import argparse
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

DONE = "_DONE"


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def quarantine(paper_dir: Path, qdir: Path, reason: str) -> None:
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / f"{paper_dir.name}.txt").write_text(reason + "\n", encoding="utf-8")
    log(f"[격리] {paper_dir.name}: {reason}")


def find_nxml(paper_dir: Path, list_csv: Path | None, qdir: Path) -> Path | None:
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

    paper_dirs = sorted(d for d in a.papers.iterdir() if d.is_dir())
    log(f"새 배가 뜬다 — 논문 폴더 {len(paper_dirs)}개")

    done_before = sum(1 for d in paper_dirs if (a.packages / d.name / DONE).exists())
    log(f"체크포인트: 이미 끝난 논문 {done_before}편은 건너뛴다")

    finished = 0
    for paper_dir in paper_dirs:
        out = a.packages / paper_dir.name
        if (out / DONE).exists():
            continue                                        # 이미 끝난 논문
        if out.exists():
            log(f"[반쪽] {paper_dir.name}: 죽다 남긴 패키지를 비우고 다시")
            shutil.rmtree(out)
        if (qdir / f"{paper_dir.name}.txt").exists():
            continue                                        # 전에 격리한 논문

        nxml = find_nxml(paper_dir, a.list, qdir)
        if nxml is None:
            continue
        try:
            r = parse_one(nxml, out, a.list)
        except IdentityMismatch as e:
            shutil.rmtree(out, ignore_errors=True)
            quarantine(paper_dir, qdir, str(e))
            continue

        finished += 1
        if a.crash_after and finished >= a.crash_after:
            log(f"[실습] {paper_dir.name} 저장 직후, _DONE 을 찍기 전에 일부러 쓰러진다 (Signal 11 흉내)")
            os._exit(11)                                    # 반쪽 패키지가 남는다 — 다음 배가 치운다

        (out / DONE).touch()                                # 끝났다는 표시 — 볼륨에 남는다
        log(f"[완료] {paper_dir.name}: 문단 {r['paragraphs']} · 그림 {r['figures']} · 표 {r['tables']}")

        if a.exit_after and finished >= a.exit_after:
            log(f"{finished}편 처리. 메모리가 눌러붙기 전에 스스로 내려간다 — 도커가 다시 띄운다")
            return 0

    log(f"전부 끝났다. 이번 배에서 {finished}편")
    return 0


if __name__ == "__main__":
    sys.exit(main())
