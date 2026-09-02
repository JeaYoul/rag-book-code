#!/usr/bin/env python3
"""
03_download.py — 선별 목록으로 본문을 받는다 (10장 ③)

받는 형태에 우선순위가 있다:
  1) .nxml 을 우선한다 — 구조(제목·그림·표·캡션)가 태그로 명시된 형태.
     파싱이 훨씬 정확해진다(12장).
  2) 없으면 .pdf 로 받는다 — 구조가 흐릿해 뒤에서 손이 많이 간다(12장).

이 스크립트는 PMC의 공개(OA) 논문을 대상으로 한다.
유료(non-OA) 논문은 여기서 받지 못한다. (본문 참고: 유럽 저장소 우회 + 단계적 구매)

⚠️ 템플릿입니다. <...> 자리를 채우고 NCBI 규칙(속도 제한)을 지키세요.

사용:
  python 03_download.py --in lists/<분야>_selected.csv --dir data/<분야>
"""

import os
import csv
import time
import argparse
import requests
from dotenv import load_dotenv
from Bio import Entrez

load_dotenv()
Entrez.email = os.getenv("NCBI_EMAIL", "<당신의_이메일@example.com>")
_api_key = os.getenv("NCBI_API_KEY", "")
if _api_key and not _api_key.startswith("<"):
    Entrez.api_key = _api_key

INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0.34"))


def pmid_to_pmcid(pmid: str) -> str | None:
    """PMID → PMCID 변환 (PMC에 본문이 있는지 확인)."""
    handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
    rec = Entrez.read(handle)
    handle.close()
    time.sleep(INTERVAL)
    try:
        linksets = rec[0].get("LinkSetDb", [])
        if not linksets:
            return None
        pmcid_num = linksets[0]["Link"][0]["Id"]
        return f"PMC{pmcid_num}"
    except (IndexError, KeyError):
        return None


def download_nxml(pmcid: str, out_dir: str) -> bool:
    """
    PMC에서 nxml(전문 XML)을 받는다. 성공하면 True.
    efetch(db=pmc, rettype=full, retmode=xml)로 받아 저장.
    """
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid.replace("PMC", ""),
                               rettype="full", retmode="xml")
        data = handle.read()
        handle.close()
        time.sleep(INTERVAL)
        if not data or len(data) < 200:  # 너무 짧으면 실패로 간주
            return False
        path = os.path.join(out_dir, f"{pmcid}.nxml")
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(path, mode) as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    [nxml 실패] {pmcid}: {e}")
        return False


def download_pdf(pmcid: str, out_dir: str) -> bool:
    """
    nxml이 없을 때 pdf를 시도한다.
    ⚠️ PMC의 pdf 직접 URL 규칙은 논문마다 다르고 변할 수 있습니다.
       아래는 자리표시자입니다. 실제 URL 해석은 환경에 맞게 구현하거나,
       (본문처럼) Claude Code 같은 도구에 위임하세요.
    """
    pdf_url = f"<PMC_PDF_URL_규칙을_여기에>"  # 예: OA 서비스 API로 실제 링크 조회
    if pdf_url.startswith("<"):
        print(f"    [pdf 보류] {pmcid}: PDF URL 규칙 미설정")
        return False
    try:
        r = requests.get(pdf_url, timeout=30)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            with open(os.path.join(out_dir, f"{pmcid}.pdf"), "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"    [pdf 실패] {pmcid}: {e}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--dir", required=True, help="저장 폴더")
    args = ap.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    with open(args.inp, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    stat = {"nxml": 0, "pdf": 0, "none": 0}
    for i, r in enumerate(rows, 1):
        pmid = r["pmid"]
        print(f"[{i}/{len(rows)}] PMID {pmid}")

        pmcid = pmid_to_pmcid(pmid)
        if not pmcid:
            print("    OA 아님(PMC 없음) → 건너뜀")
            stat["none"] += 1
            continue

        # nxml 우선, 없으면 pdf
        if download_nxml(pmcid, args.dir):
            print(f"    ✓ nxml 저장 ({pmcid})")
            stat["nxml"] += 1
        elif download_pdf(pmcid, args.dir):
            print(f"    ✓ pdf 저장 ({pmcid})")
            stat["pdf"] += 1
        else:
            print(f"    ✗ 본문 확보 실패 ({pmcid})")
            stat["none"] += 1

    print(f"\n완료: nxml {stat['nxml']} · pdf {stat['pdf']} · 실패/비OA {stat['none']}")
    print("→ 이제 04_verify.py 로 메타데이터를 검증하세요.")


if __name__ == "__main__":
    main()
