#!/usr/bin/env python3
"""
pipeline.py — 질문 하나가 조각 다섯이 되기까지 (16장 그림 그대로)

    python pipeline.py "낙산균이 대장 염증에 미치는 효과는?" --memory ../ch15-embedding/embedded/*.jsonl --fake
    python pipeline.py "..." --pg                      # 실제: pgvector + Qwen 리랭커(→bge 폴백) + bge-m3

흐름:  리라이팅(옮기고·쪼개고) → 서브쿼리마다 [두 벌 검색 15개 → 리랭커 10개 → 논문당 둘 → 5개]
       → 합쳐서 중복 제거 → 머리글 없는 글 + 출처로 컨텍스트 → (원하면) LLM
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ch15-embedding"))   # embed.Encoder 를 빌린다

from query_rewrite import prepare_queries
from rerank import FakeReranker, deduplicate_chunks, rerank_documents
from search import MemoryBackend, retrieve_unified_chunks

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")


def enhanced_search(question, backend, encoder, top_k=5, use_llm=True, reranker=None):
    """서브쿼리마다 k*3 → 리랭커 k*2 → 논문당 둘 → k. 실제 enhanced_search 와 같은 배수."""
    pairs = prepare_queries(question, use_llm=use_llm)          # [(한국어, 영어), ...]
    merged, seen, per_query = [], set(), []
    for ko, en in pairs:
        raw = retrieve_unified_chunks(ko, backend, encoder, k=top_k * 3, en_question=en)
        kw = {"primary": reranker, "fallback": reranker} if reranker else {}
        ranked = rerank_documents(en or ko, raw, top_k=top_k * 2, **kw)
        picked = deduplicate_chunks(ranked, max_per_paper=2)[:top_k]
        uniq = []
        for c in picked:
            key = (c["paper_id"], c["content"][:80])
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        per_query.append({"query": ko, "query_en": en, "raw": len(raw), "chunks": uniq})
        merged.extend(uniq)
    return {"is_decomposed": len(pairs) > 1, "sub_queries": pairs, "results": per_query,
            "merged_chunks": merged, "unique_papers": len({c["paper_id"] for c in merged})}


def build_context(chunks):
    """LLM 에 건넬 글 — 조각 본문 + 출처 번호. (content_for_llm 은 실제 DB 에서 비어 있어 content 를 쓴다)"""
    return "\n\n".join(f"[{i + 1}] {c.get('paper_title', '')} — {c.get('section', '')}\n{c['content']}"
                       for i, c in enumerate(chunks))


def ask_llm(context, question, max_tokens=2048):
    """12장의 메인 LLM 에게. 근거에 없으면 모른다고 하라."""
    import os
    import requests
    r = requests.post(f"{os.getenv('LLM_BASE_URL', 'http://localhost:4000/v1')}/chat/completions", json={
        "model": os.getenv("LLM_MODEL", "qwen"), "max_tokens": max_tokens, "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": "다음 자료만 근거로 답하라. 자료에 없으면 모른다고 하라. 근거 번호 [n] 을 달아라."},
            {"role": "user", "content": f"[자료]\n{context}\n\n[질문]\n{question}"},
        ]}, timeout=120)
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    return msg.get("content") or msg.get("reasoning_content") or "(빈 응답)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--memory", nargs="*", help="15장 embed.py 가 만든 *.embedded.jsonl (DB 없이)")
    ap.add_argument("--pg", action="store_true", help="실제 PostgreSQL (PG_DSN)")
    ap.add_argument("--fake", action="store_true", help="가짜 벡터·가짜 리랭커·LLM 없이 (실습용)")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ask", action="store_true", help="마지막에 LLM 에게 답을 시킨다")
    a = ap.parse_args()

    from embed import Encoder
    encoder = Encoder(fake=a.fake)
    if a.pg:
        from search import PgBackend
        backend = PgBackend()
    elif a.memory:
        backend = MemoryBackend(a.memory)
    else:
        ap.error("--memory 파일들 또는 --pg 를 주어라")

    res = enhanced_search(a.question, backend, encoder, top_k=a.top_k,
                          use_llm=not a.fake, reranker=FakeReranker() if a.fake else None)
    print(f"복합 질문: {res['is_decomposed']} · 서브쿼리 {len(res['sub_queries'])}개")
    for r in res["results"]:
        print(f"  · {r['query']}  →  {r['query_en']}   (후보 {r['raw']} → {len(r['chunks'])})")
        for c in r["chunks"]:
            print(f"      {c['rerank_score']:.3f} {c['hits']:5s} {c['paper_id']} [{c['chunk_type']}] {c['section'][:30]}")
    print(f"근거 {len(res['merged_chunks'])}조각 · 논문 {res['unique_papers']}편")
    ctx = build_context(res["merged_chunks"])
    print(f"컨텍스트 {len(ctx):,}자")
    if a.ask:
        print("\n" + ask_llm(ctx, a.question))
    return 0


if __name__ == "__main__":
    sys.exit(main())
