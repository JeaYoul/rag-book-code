#!/usr/bin/env python3
"""
paper_guardian.py — 월요일 아침의 논문 (21장)

    python paper_guardian.py --dry-run     검색어와 건수만 (요약 안 함)
    python paper_guardian.py               PubMed 조회 → 모델 요약 → 알림
    python paper_guardian.py --fake        바깥 API 없이 흐름만

두 번의 실패가 이 파일에 흔적으로 남아 있다.

1) 오탐 — 화합물 이름을 넓게 잡았더니 그 화합물을 *시약으로 쓴* 논문이 딸려 왔다.
   그래서 [Title/Abstract] 로 한정했다. 시약은 대개 본문 실험 방법에만 나온다.
2) 오역 — 모델이 학명을 임의로 한국어로 옮겼다. 돌고래를 범고래로 바꿔 놓기도 했다.
   그래서 지시문에 못을 박았다: 모르면 번역하지 마라.
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import send   # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
LLM = os.getenv("LLM_URL", "http://localhost:4000/v1/chat/completions")
MODEL = os.getenv("LLM_MODEL", "qwen")
DAYS = int(os.getenv("PAPER_DAYS", "7"))
PER_TOPIC = int(os.getenv("PAPER_PER_TOPIC", "5"))
TOOL, MAIL = "rag-book-guardian", os.getenv("NCBI_EMAIL", "")
FAKE = False

# 감시축. [Title/Abstract] 가 오탐을 막는 그 한정이다
TOPICS = [
    ("후생유전학과 식이성분",
     '(epigenetic*[Title/Abstract] OR "DNA methylation"[Title/Abstract] OR histone[Title/Abstract]) '
     'AND (dietary[Title/Abstract] OR phytochemical[Title/Abstract] OR polyphenol[Title/Abstract])'),
    ("설포라판·브로콜리 스프라우트",
     '(sulforaphane[Title/Abstract] OR "broccoli sprout"[Title/Abstract] '
     'OR glucoraphanin[Title/Abstract] OR glucosinolate[Title/Abstract])'),
    ("낙산균·단쇄지방산",
     '(butyrate[Title/Abstract] OR "short-chain fatty acid"[Title/Abstract]) '
     'AND (microbiome[Title/Abstract] OR "gut microbiota"[Title/Abstract])'),
]

SUM_SYS = ("당신은 건강기능식품 연구소의 논문 요약 담당입니다. "
           "주어진 논문의 제목과 초록을 읽고 한국어 두세 문장으로 요약하세요. "
           "무엇을 밝혀냈는지와 그것이 왜 의미 있는지를 중심으로 쓰고, "
           "마크다운 기호나 목록은 쓰지 말고 평범한 문장으로만 쓰세요. "
           "학명, 생물 종명, 화합물명, 유전자명, 균주명은 영문 원문을 그대로 쓰거나 "
           "한국어 뒤에 괄호로 영문을 병기하세요. 정확한 한국어 명칭을 모르면 "
           "추측해서 번역하지 말고 영문 학명을 그대로 두세요. "
           "특히 동물 종명은 임의로 한국어 통칭을 붙이지 마세요. "
           "초록에 없는 내용은 절대 지어내지 마세요.")

_last = 0.0


def _wait():
    """NCBI 는 연달아 두드리면 막는다. 호출 사이를 벌린다."""
    global _last
    gap = 0.4 - (time.time() - _last)
    if gap > 0:
        time.sleep(gap)
    _last = time.time()


def esearch(term):
    if FAKE:                                   # 주제마다 다른 번호가 나오게 (중복 제거를 보려면)
        n = abs(hash(term)) % 900 + 100
        return [f"400{n}01", f"400{n}02"]
    import requests
    _wait()
    p = {"db": "pubmed", "term": term, "retmax": PER_TOPIC, "retmode": "json",
         "sort": "date", "reldate": DAYS, "datetype": "edat", "tool": TOOL}
    if MAIL:
        p["email"] = MAIL
    r = requests.get(f"{EUTILS}/esearch.fcgi", params=p, timeout=60)
    r.raise_for_status()
    return r.json()["esearchresult"].get("idlist", [])


def esummary(pmids):
    if FAKE:
        return [{"pmid": p, "title": f"(fake) paper {p}", "journal": "J Fake", "year": "2026"} for p in pmids]
    if not pmids:
        return []
    import requests
    _wait()
    r = requests.get(f"{EUTILS}/esummary.fcgi",
                     params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json", "tool": TOOL}, timeout=60)
    r.raise_for_status()
    d = r.json().get("result", {})
    return [{"pmid": i, "title": d.get(i, {}).get("title", ""),
             "journal": d.get(i, {}).get("fulljournalname", ""),
             "year": (d.get(i, {}).get("pubdate") or "")[:4]} for i in pmids]


def summarize(paper):
    if FAKE:
        return "(fake) 이 논문은 무엇을 밝혔고 왜 의미 있는지를 두세 문장으로."
    import requests
    r = requests.post(LLM, json={"model": MODEL,
                                 "messages": [{"role": "system", "content": SUM_SYS},
                                              {"role": "user", "content": f"제목: {paper['title']}"}],
                                 "max_tokens": 800, "temperature": 0.3,
                                 "chat_template_kwargs": {"enable_thinking": False}}, timeout=300)
    r.raise_for_status()
    m = r.json()["choices"][0]["message"]
    return (m.get("content") or m.get("reasoning_content") or "").strip()


def main():
    global FAKE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="검색만 하고 요약·발송은 하지 않는다")
    ap.add_argument("--fake", action="store_true", help="바깥 API 없이 흐름만")
    a = ap.parse_args()
    FAKE = a.fake

    seen, groups = set(), []
    for name, term in TOPICS:
        ids = [i for i in esearch(term) if i not in seen]
        seen.update(ids)
        groups.append((name, esummary(ids)))
        print(f"· {name}: {len(ids)}편")

    total = sum(len(p) for _, p in groups)
    if a.dry_run:
        print(f"\n합계 {total}편. (--dry-run 이라 요약도 발송도 하지 않는다)")
        # 읽어 낸 건수 자체를 지켜보는 것이 먼저다 — 0편이 계속되면
        # 새 논문이 없는 것이 아니라 검색이 고장 난 것일 수 있다 (21장 공모사업 절)
        return 0

    lines = [f"📚 논문 파수꾼 — 최근 {DAYS}일"]
    if total == 0:
        lines.append("\n조건에 맞는 신규 논문이 없습니다.")
    for name, papers in groups:
        if not papers:
            continue
        lines.append(f"\n■ {name}")
        for p in papers:
            lines.append(f"\n[{p['pmid']}] {p['title']}")
            lines.append(f"  {p['journal']} {p['year']}")
            s = summarize(p)
            if s:
                lines.append(f"  {s}")
    send("\n".join(lines))
    print(f"합계 {total}편 발송")
    return 0


if __name__ == "__main__":
    sys.exit(main())
