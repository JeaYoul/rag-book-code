#!/usr/bin/env python3
"""
verify_citations.py — 답에 적힌 논문 번호가 정말 있는가 (17장 "흔들리지 않는 자")

    python verify_citations.py results/open.json --pg                 # DB 에서 대조
    python verify_citations.py results/open.json --known-from corpus/*.jsonl   # DB 없이 — 코퍼스의 ID 로 대조

답에서 PMC 번호를 전부 뽑아, 하나씩 "SELECT 1 FROM papers WHERE paper_id = %s" 로 확인한다.
있으면 실재, 없으면 지어낸 것. 사람도 모델도 끼지 않는다 — 내일 다시 돌려도 같은 숫자.
결과는 같은 파일의 문항마다 citation_verification 으로, 파일 머리에 citation_summary 로 덧붙인다.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

PMC_RE = re.compile(r"PMC\d{5,9}")
PAPERS_TABLE = os.getenv("PAPERS_TABLE", "papers")


def known_ids_from_files(files):
    ids = set()
    for f in files:
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["paper_id"])
    return ids


class PgChecker:
    def __init__(self):
        import psycopg2
        self.conn = psycopg2.connect(os.getenv("PG_DSN"))

    def exists(self, pmc_id):
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM {PAPERS_TABLE} WHERE paper_id = %s LIMIT 1", (pmc_id,))
            return cur.fetchone() is not None


def verify(answer, exists):
    ids = list(dict.fromkeys(PMC_RE.findall(answer)))          # 순서 유지, 중복 제거
    verified = [i for i in ids if exists(i)]
    hallucinated = [i for i in ids if i not in verified]
    return {"total": len(ids), "verified": len(verified), "hallucinated": len(hallucinated),
            "hallucination_rate": round(len(hallucinated) / len(ids), 4) if ids else 0.0,
            "verified_ids": verified, "hallucinated_ids": hallucinated}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path)
    ap.add_argument("--pg", action="store_true")
    ap.add_argument("--known-from", nargs="*", help="DB 없이 — 이 jsonl 들의 paper_id 를 '실재' 로 본다")
    a = ap.parse_args()

    if a.pg:
        exists = PgChecker().exists
    elif a.known_from:
        known = known_ids_from_files(a.known_from)
        exists = known.__contains__
    else:
        ap.error("--pg 또는 --known-from 을 주어라")

    d = json.loads(a.results.read_text(encoding="utf-8"))
    tot = {"total": 0, "verified": 0, "hallucinated": 0}
    for r in d["results"]:
        v = verify(r.get("answer", ""), exists)
        r["citation_verification"] = v
        for k in tot:
            tot[k] += v[k]
        flag = f"  ⚠ 지어냄 {v['hallucinated_ids']}" if v["hallucinated"] else ""
        print(f"[{r['id']}] 인용 {v['verified']}/{v['total']} 실재{flag}")
    d["citation_summary"] = {**tot, "overall_hallucination_rate":
                             round(tot["hallucinated"] / tot["total"], 4) if tot["total"] else 0.0}
    a.results.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n합계: 인용 {tot['total']}개 · 실재 {tot['verified']} · 지어냄 {tot['hallucinated']} "
          f"({d['citation_summary']['overall_hallucination_rate']:.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
