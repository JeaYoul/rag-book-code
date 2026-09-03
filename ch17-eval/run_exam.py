#!/usr/bin/env python3
"""
run_exam.py — 시스템에 시험을 보게 한다 (17장 "문제지 만들기")

    python run_exam.py testset.json --mode open   --out results/open.json   [--pg | --memory *.jsonl] [--fake]
    python run_exam.py testset.json --mode closed --out results/closed.json [--fake]

두 벌 시험:
    closed  근거 없이 LLM 혼자 (1장의 폐쇄형 시험)
    open    16장의 검색 파이프라인으로 근거를 찾아 주고 (오픈북)

문제지는 고정한다. 같은 30문항으로 매번 잰다.
결과 파일에는 문항마다 질문·모범답·답·가져온 근거·걸린 시간을 적는다.
점수는 evaluate.py 가 같은 파일에 덧붙인다 — "적어 두지 않은 숫자는 사라진다".

--fake 면 LLM 없이 근거 문장을 베껴 답을 만든다 (흐름 실습용).
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ch16-retrieval"))
sys.path.insert(0, str(HERE.parent / "ch15-embedding"))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")


def fake_answer(question, chunks):
    """모델 없이 — 근거의 첫 문장들을 이어 붙이고 [PMCID] 를 단다. 지어낸 인용도 하나 섞는다 (검증기가 잡는지 보려고)."""
    lines = []
    for c in chunks[:3]:
        first = re.split(r"(?<=[.!?])\s+", c["content"].strip())[0][:200]
        lines.append(f"{first} [{c['paper_id']}]")
    lines.append("이 효과는 여러 연구에서 재현되었다 [PMC0000000].")   # 없는 논문 — 검증기가 잡아야 한다
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("testset", type=Path)
    ap.add_argument("--mode", choices=["open", "closed"], default="open")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pg", action="store_true")
    ap.add_argument("--memory", nargs="*")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--top-k", type=int, default=5)
    a = ap.parse_args()

    testset = json.loads(a.testset.read_text(encoding="utf-8"))
    backend = encoder = None
    if a.mode == "open":
        from embed import Encoder
        from search import MemoryBackend
        encoder = Encoder(fake=a.fake)
        if a.pg:
            from search import PgBackend
            backend = PgBackend()
        elif a.memory:
            backend = MemoryBackend(a.memory)
        else:
            ap.error("open 모드는 --pg 또는 --memory 가 필요하다")
    from pipeline import ask_llm, build_context, enhanced_search
    from rerank import FakeReranker

    results = []
    for item in testset:
        t0 = time.time()
        contexts, search_sec = [], 0.0
        if a.mode == "open":
            ts = time.time()
            res = enhanced_search(item["question"], backend, encoder, top_k=a.top_k,
                                  use_llm=not a.fake, reranker=FakeReranker() if a.fake else None)
            search_sec = time.time() - ts
            contexts = [{"paper_id": c["paper_id"], "chunk_id": c["chunk_id"], "section": c.get("section", ""),
                         "rerank_score": c.get("rerank_score"), "content": c["content"]} for c in res["merged_chunks"]]
        if a.fake:
            answer = fake_answer(item["question"], contexts) if contexts else "근거 없음 [PMC0000000]"
        elif a.mode == "open":
            answer = ask_llm(build_context(res["merged_chunks"]), item["question"])
        else:
            answer = ask_llm("(자료 없음 — 아는 대로 답하라)", item["question"])
        results.append({**item, "answer": answer, "contexts": contexts,
                        "search_elapsed_sec": round(search_sec, 2), "elapsed_sec": round(time.time() - t0, 2)})
        print(f"[{item['id']}] {item['question'][:40]}  근거 {len(contexts)} · {results[-1]['elapsed_sec']}s")

    out = {"eval_date": datetime.now().isoformat(timespec="seconds"), "mode": a.mode, "fake": a.fake,
           "total_questions": len(results), "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in results) / max(1, len(results)), 2),
           "results": results}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(results)}문항 → {a.out}  (평균 {out['avg_elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
