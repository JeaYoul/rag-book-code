"""
7장. 당신에게는 직관이 있다 — 첫 번째 자동화
《산골 농부의 RAG》 예제 코드

당신 분야의 최근 논문이 몇 편이고, 무엇이 중요한지 알고 싶은 적이 있는가?

손으로 하려면:
    검색하고 → 목록 보고 → 하나씩 클릭하고 → 제목 베끼고 → 인용수 찾아보고...
    논문 10만 편이면? 평생 걸린다. 사실상 불가능하다.

이 스크립트로 하면:
    한 시간이면 끝난다. 엑셀 파일 하나에 전부 정리되어 나온다.

이것이 AI에게 맡겨야 할 일의 전형이다.
  · 단순하고
  · 반복적이고
  · 양이 압도적이고
  · 그래서 인간이 하기에는 불가능한 일

[준비]
    pip install requests pandas openpyxl

[실행]
    python pubmed_survey.py

[검색어 바꾸기]
    아래 QUERY 를 당신 분야의 검색어로 바꾸면 된다.
    PubMed 검색창에서 쓰는 문법을 그대로 쓸 수 있다.
"""

import time
import requests
import pandas as pd


# ─────────────────────────────────────────────
# 여기만 당신 분야에 맞게 바꾸면 된다
# ─────────────────────────────────────────────
QUERY = "sulforaphane AND broccoli"     # 검색어 (PubMed 검색 문법 그대로)
YEARS = 10                              # 최근 몇 년
MAX_PAPERS = 500                        # 가져올 최대 편수 (처음엔 작게 시작하라!)
OUTPUT = "papers.xlsx"                  # 결과 엑셀 파일

# NCBI 예의: 이메일을 남기고, 초당 요청 수를 지킨다.
EMAIL = "your@email.com"                # 당신 이메일로 바꾸세요

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ICITE = "https://icite.od.nih.gov/api/pubs"


# ─────────────────────────────────────────────
# ① 검색 — 조건에 맞는 논문의 ID 목록을 받는다
# ─────────────────────────────────────────────
# PubMed에 "이런 논문 찾아줘"라고 물으면, 논문마다 붙은 고유번호(PMID) 목록을 준다.
# 도서관에서 책 청구기호 목록을 받는 것과 같다.
def search_pubmed(query, years, max_papers):
    print(f"[검색] '{query}' — 최근 {years}년")

    res = requests.get(f"{EUTILS}/esearch.fcgi", params={
        "db": "pubmed",
        "term": query,
        "reldate": years * 365,      # 최근 N년
        "datetype": "pdat",
        "retmax": max_papers,
        "retmode": "json",
        "email": EMAIL,
    })
    data = res.json()["esearchresult"]

    total = int(data["count"])
    pmids = data["idlist"]

    print(f"  → 조건에 맞는 논문: 총 {total:,}편")
    print(f"  → 이번에 가져올 것: {len(pmids):,}편")
    return pmids


# ─────────────────────────────────────────────
# ② 메타데이터 — 제목·저자·저널·연도를 받는다
# ─────────────────────────────────────────────
# 200편씩 나눠서 요청한다. 한 번에 다 달라고 하면 서버가 거절한다.
def fetch_metadata(pmids):
    print(f"[메타데이터] {len(pmids):,}편 가져오는 중...")
    papers = []

    for i in range(0, len(pmids), 200):
        batch = pmids[i:i + 200]

        res = requests.get(f"{EUTILS}/esummary.fcgi", params={
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "json",
            "email": EMAIL,
        })
        result = res.json().get("result", {})

        for pmid in batch:
            item = result.get(pmid)
            if not item:
                continue
            authors = [a["name"] for a in item.get("authors", [])]
            papers.append({
                "PMID": pmid,
                "제목": item.get("title", ""),
                "저자": ", ".join(authors[:3]) + (" 외" if len(authors) > 3 else ""),
                "저널": item.get("fulljournalname", ""),
                "발행일": item.get("pubdate", ""),
                "DOI": item.get("elocationid", ""),
            })

        print(f"  → {min(i + 200, len(pmids)):,} / {len(pmids):,}")
        time.sleep(0.4)      # NCBI 예의: 초당 3회 이하

    return papers


# ─────────────────────────────────────────────
# ③ 인용수 — 이 논문이 몇 번이나 인용됐나
# ─────────────────────────────────────────────
# NIH의 iCite 서비스가 인용수를 무료로 알려준다.
# 인용수는 '이 논문이 얼마나 중요하게 받아들여졌는가'의 신호다.
def fetch_citations(pmids):
    print(f"[인용수] {len(pmids):,}편 조회 중...")
    citations = {}

    for i in range(0, len(pmids), 200):
        batch = pmids[i:i + 200]

        res = requests.get(ICITE, params={
            "pmids": ",".join(batch),
            "fl": "pmid,citation_count",     # 필요한 것만 요청
        })
        for item in res.json().get("data", []):
            citations[str(item["pmid"])] = item.get("citation_count", 0)

        print(f"  → {min(i + 200, len(pmids)):,} / {len(pmids):,}")
        time.sleep(0.4)

    return citations


# ─────────────────────────────────────────────
# 실행 — 세 단계를 이어 붙이면 끝
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # ① 검색
    pmids = search_pubmed(QUERY, YEARS, MAX_PAPERS)
    if not pmids:
        print("검색 결과가 없습니다. 검색어를 확인하세요.")
        exit()

    # ② 메타데이터
    papers = fetch_metadata(pmids)

    # ③ 인용수 붙이기
    citations = fetch_citations(pmids)
    for p in papers:
        p["인용수"] = citations.get(p["PMID"], 0)

    # ④ 엑셀로 저장 — 인용수가 많은 순으로 정렬
    df = pd.DataFrame(papers)
    df = df.sort_values("인용수", ascending=False)
    df.to_excel(OUTPUT, index=False)

    print()
    print("=" * 55)
    print(f"완료!  '{OUTPUT}' 파일이 만들어졌습니다.")
    print("=" * 55)
    print(f"  논문 {len(df):,}편, 인용수 많은 순으로 정렬됨")
    print()
    print("  가장 많이 인용된 논문 5편:")
    for _, row in df.head(5).iterrows():
        print(f"    [{row['인용수']:>5}회] {row['제목'][:55]}...")
    print()
    print("이제 엑셀을 열어보라.")
    print("당신 분야의 지형도가, 한눈에 들어올 것이다.")


# ─────────────────────────────────────────────
# 다음 단계 — AI에게 이렇게 시켜보라
# ─────────────────────────────────────────────
# 이 스크립트는 출발점일 뿐이다. 여기서 당신 분야에 맞게 키워 나가면 된다.
# 코드를 직접 고칠 필요는 없다. AI에게 이렇게 말하면 된다.
#
#   "이 스크립트에 초록(abstract)도 함께 가져오게 해줘"
#   "저널별로 시트를 나눠서 엑셀에 저장해줘"
#   "연도별 논문 수를 그래프로 그려줘"
#   "특정 저자의 논문만 따로 뽑아줘"
#   "10만 편을 가져오려면 어떻게 해야 해? 중간에 끊겨도 이어서 하게 해줘"
#                                         (↑ 2장의 불사조가 여기서 다시 등장한다)
#
# 막히면 에러 메시지를 그대로 복사해서 던져라.
# 그것이 이 책이 알려주는 가장 중요한 기술이다.
