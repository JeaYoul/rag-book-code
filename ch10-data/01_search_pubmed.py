#!/usr/bin/env python3
"""
01_search_pubmed.py — 한 분야를 검색해 '목록'을 만든다 (10장 ①)

이 장의 핵심: 본문을 먼저 받지 않는다. **목록이 먼저다.**
검색과 동시에 선별용 메타데이터(제목·저자·일자·소속·분야)를 함께 받아
CSV 목록으로 저장한다. 이 목록이 곧 선별의 근거다.

⚠️ 템플릿입니다. <...> 자리를 채우고, 검색어를 당신 분야로 바꾸세요.

사용:
  python 01_search_pubmed.py --query "<검색어>" --years 10 --out lists/<분야>.csv

준비:
  pip install biopython python-dotenv
  cp config.example.env .env   # 이메일·API 키 채우기
"""

import os
import csv
import time
import argparse
from dotenv import load_dotenv
from Bio import Entrez

load_dotenv()
Entrez.email = os.getenv("NCBI_EMAIL", "<당신의_이메일@example.com>")
_api_key = os.getenv("NCBI_API_KEY", "")
if _api_key and not _api_key.startswith("<"):
    Entrez.api_key = _api_key

INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0.34"))


def build_query(term: str, years: int) -> str:
    """
    검색식을 만든다.
    - 최근 N년으로 좁혀 '한 번에 다루기 좋은 크기'로 자른다.
    - 동의어 확장: 같은 물질의 별칭을 OR로 묶는다.
      예) ("sulforaphane" OR "SFN" OR "설포라판")
    필요하면 여기에 자기 분야 별칭을 더 넣으세요.
    """
    # <동의어_확장> — 아래 리스트를 당신 분야의 별칭으로 바꾸세요.
    synonyms = [term]  # 예: [term, "SFN", "설포라판"]
    or_block = " OR ".join(f'"{s}"' for s in synonyms)
    # 최근 N년 필터 + 초록 있는 것 위주(선택)
    return f'({or_block}) AND ("last {years} years"[dp])'


def search_ids(query: str, retmax: int) -> list[str]:
    """검색 → PMID 목록."""
    handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax)
    rec = Entrez.read(handle)
    handle.close()
    time.sleep(INTERVAL)
    return rec.get("IdList", [])


def fetch_metadata(pmids: list[str]) -> list[dict]:
    """
    PMID 목록 → 선별용 메타데이터.
    한 번에 다 부으면 넘친다. 여기서도 batch로 나눠 받는다.
    """
    rows: list[dict] = []
    BATCH = 100
    for i in range(0, len(pmids), BATCH):
        chunk = pmids[i:i + BATCH]
        handle = Entrez.efetch(db="pubmed", id=",".join(chunk),
                               rettype="medline", retmode="xml")
        records = Entrez.read(handle)
        handle.close()

        for art in records.get("PubmedArticle", []):
            try:
                cit = art["MedlineCitation"]
                article = cit["Article"]
                pmid = str(cit["PMID"])
                title = str(article.get("ArticleTitle", ""))

                # 저자 (첫 저자 + 외 N명)
                authors = article.get("AuthorList", [])
                first = ""
                if authors:
                    a0 = authors[0]
                    first = f'{a0.get("LastName","")} {a0.get("ForeName","")}'.strip()
                author_str = first + (f" 외 {len(authors)-1}명" if len(authors) > 1 else "")

                # 소속 (첫 저자 소속, 간단히)
                affil = ""
                if authors and authors[0].get("AffiliationInfo"):
                    affil = authors[0]["AffiliationInfo"][0].get("Affiliation", "")

                # 발행 연도
                year = ""
                dp = article.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
                year = dp.get("Year", "") or dp.get("MedlineDate", "")

                journal = str(article.get("Journal", {}).get("Title", ""))

                rows.append({
                    "pmid": pmid,
                    "title": title,
                    "authors": author_str,
                    "year": year,
                    "journal": journal,
                    "affiliation": affil[:120],  # 너무 길면 자름
                })
            except Exception as e:
                # 개별 논문 파싱 실패는 건너뛴다 (불사조 정신: 하나 죽어도 계속)
                print(f"  [skip] {e}")
                continue

        time.sleep(INTERVAL)
        print(f"  메타데이터 {min(i+BATCH, len(pmids))}/{len(pmids)} 수집")
    return rows


def save_csv(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fields = ["pmid", "title", "authors", "year", "journal", "affiliation"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"목록 저장: {out_path}  ({len(rows)}편)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="검색어(분야). 예: sulforaphane")
    ap.add_argument("--years", type=int, default=10, help="최근 N년")
    ap.add_argument("--retmax", type=int, default=1000, help="이 분야 최대 수집 편수")
    ap.add_argument("--out", required=True, help="목록 저장 경로(csv)")
    args = ap.parse_args()

    query = build_query(args.query, args.years)
    print(f"검색식: {query}")

    pmids = search_ids(query, args.retmax)
    print(f"검색 결과: {len(pmids)}편")

    rows = fetch_metadata(pmids)
    save_csv(rows, args.out)
    print("→ 이제 02_select.py 로 받을 대상을 선별하세요.")


if __name__ == "__main__":
    main()
