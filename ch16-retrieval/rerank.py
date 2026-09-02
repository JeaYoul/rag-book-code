#!/usr/bin/env python3
"""
rerank.py — 2단 심사와 논문당 둘 규칙 (16장 "리랭커 — 2단 심사")

    rerank_documents(query, docs, top_k)
        주력  Qwen3-Reranker-8B — Spark2 :8090 HTTP (/v1/rerank), 30초
        예비  bge-reranker-v2-m3 — 같은 프로세스 안의 CrossEncoder
        실습  FakeReranker — 모델 없이 낱말 겹침으로 점수 (뜻은 없다)
        조각은 앞 8,000자만 넣는다.

    deduplicate_chunks(chunks, max_per_paper=2, high_score_threshold=0.95)
        같은 내용은 하나만 · 논문의 첫 조각은 늘 · 둘째는 점수 0.95↑ 일 때만 · 셋째부터 안 들임
"""
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

QWEN3_RERANKER_URL = os.getenv("QWEN3_RERANKER_URL", "http://192.168.10.51:8090/v1/rerank")
RERANKER_HTTP_TIMEOUT = float(os.getenv("RERANKER_HTTP_TIMEOUT", "30"))
FALLBACK_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
DOC_CHARS = 8000


class QwenHttpReranker:
    """주력. 서버가 30초 안에 답하지 않으면 예외 — 호출한 쪽이 폴백한다."""

    def score(self, query, docs):
        import requests
        r = requests.post(QWEN3_RERANKER_URL,
                          json={"query": query, "documents": [d["content"][:DOC_CHARS] for d in docs]},
                          timeout=RERANKER_HTTP_TIMEOUT)
        r.raise_for_status()
        results = r.json()["results"]                      # [{index, relevance_score}, ...]
        scores = [0.0] * len(docs)
        for item in results:
            scores[item["index"]] = float(item["relevance_score"])
        return scores


class BgeCrossEncoderReranker:
    """예비. 처음 부를 때 모델을 올린다."""
    _model = None

    def score(self, query, docs):
        if BgeCrossEncoderReranker._model is None:
            from sentence_transformers import CrossEncoder
            BgeCrossEncoderReranker._model = CrossEncoder(FALLBACK_MODEL, max_length=4096)
        pairs = [[query, d["content"][:DOC_CHARS]] for d in docs]
        return [float(s) for s in BgeCrossEncoderReranker._model.predict(pairs)]


class FakeReranker:
    """실습용. 질문의 낱말이 조각에 얼마나 겹치는지 — 결정적이고 모델이 없다."""

    def score(self, query, docs):
        q = set(re.findall(r"[a-zA-Z가-힣0-9]{2,}", query.lower()))
        out = []
        for d in docs:
            words = re.findall(r"[a-zA-Z가-힣0-9]{2,}", d["content"][:DOC_CHARS].lower())
            hit = sum(1 for w in words if w in q)
            out.append(round(min(1.0, hit / max(1, len(q))), 4))
        return out


def rerank_documents(query, docs, top_k=5, primary=None, fallback=None):
    """주력 → 실패하면 예비. 점수를 rerank_score 에 적고 상위 top_k."""
    if not docs:
        return []
    primary = primary or QwenHttpReranker()
    fallback = fallback or BgeCrossEncoderReranker()
    try:
        scores = primary.score(query, docs)
        used = type(primary).__name__
    except Exception as e:                                   # 죽었거나 30초를 넘겼다
        print(f"  [리랭커] 주력 실패({type(e).__name__}) → 예비로", file=sys.stderr)
        scores = fallback.score(query, docs)
        used = type(fallback).__name__
    for d, s in zip(docs, scores):
        d["rerank_score"] = float(s)
        d["reranker"] = used
    return sorted(docs, key=lambda d: d["rerank_score"], reverse=True)[:top_k]


def deduplicate_chunks(chunks, max_per_paper=2, high_score_threshold=0.95):
    """리랭커 점수 순으로 들어온 조각에서 — 같은 내용 하나만, 논문당 최대 둘(둘째는 점수 높을 때만)."""
    seen_papers, seen_content, result = {}, set(), []
    for c in chunks:
        key = c["content"][:100]
        if key in seen_content:
            continue
        seen_content.add(key)
        pid = c["paper_id"]
        n = seen_papers.get(pid, 0)
        score = c.get("rerank_score", c.get("similarity", 0))
        if n == 0:
            result.append(c)
            seen_papers[pid] = 1
        elif n < max_per_paper and score >= high_score_threshold:
            result.append(c)
            seen_papers[pid] += 1
    return result
