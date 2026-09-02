#!/usr/bin/env python3
"""
search.py — 찾아내기 (16장 "벡터 검색만으로는 부족하다" · "하이브리드 검색")

두 백엔드가 같은 얼굴을 갖는다:
    PgBackend      pgvector SQL — ORDER BY embedding <=> q · 참고문헌 제외 · HNSW
                   벡터+키워드(tsvector, ts_rank_cd) 7:3 도 여기 (평가용, 17장)
    MemoryBackend  15장 embed.py 가 만든 *.embedded.jsonl 을 읽어 numpy 로 — DB 없이 실습

두 벌 검색:
    retrieve_unified_chunks(question, backend, encoder)
        한국어 질문으로 20개 + 영어로 옮긴 질문으로 20개 → 합치고 중복 제거 (HYBRID_WEIGHT 0.5)
"""
import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

RAG_TOP_K = int(os.getenv("RAG_TOP_K", 20))
HYBRID_WEIGHT = float(os.getenv("HYBRID_WEIGHT", 0.5))   # 한국어 판 : 영어 판


# ---------------------------------------------------------------- 백엔드

class PgBackend:
    """실제 경로. PG_DSN 으로 붙는다."""

    def __init__(self, dsn=None):
        import psycopg2
        self.conn = psycopg2.connect(dsn or os.getenv("PG_DSN"))

    @staticmethod
    def _vec(v):
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    def vector_search(self, qvec, k=RAG_TOP_K):
        sql = """
            SELECT c.chunk_id, c.paper_id, c.chunk_type, c.section, c.content_for_llm, p.title,
                   1 - (c.embedding <=> %s::vector) AS similarity
            FROM chunks c JOIN papers p USING (paper_id)
            WHERE NOT c.is_reference_section AND c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s"""
        with self.conn.cursor() as cur:
            cur.execute(sql, (self._vec(qvec), self._vec(qvec), k))
            return [self._row(r) for r in cur.fetchall()]

    def hybrid_vector_bm25(self, qvec, qtext, k=RAG_TOP_K, vector_weight=0.7, bm25_weight=0.3):
        """벡터 점수와 키워드 점수를 섞는다 — 실제 시스템에서는 평가(17장)에 쓴다."""
        sql = """
            WITH v AS (
                SELECT chunk_id, 1 - (embedding <=> %s::vector) AS vscore
                FROM chunks WHERE NOT is_reference_section AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector LIMIT %s),
            b AS (
                SELECT chunk_id, ts_rank_cd(content_tsv, plainto_tsquery('english', %s)) AS bscore
                FROM chunks WHERE NOT is_reference_section
                  AND content_tsv @@ plainto_tsquery('english', %s)
                ORDER BY bscore DESC LIMIT %s)
            SELECT c.chunk_id, c.paper_id, c.chunk_type, c.section, c.content_for_llm, p.title,
                   %s * COALESCE(v.vscore, 0) + %s * COALESCE(b.bscore, 0) AS similarity
            FROM chunks c JOIN papers p USING (paper_id)
            LEFT JOIN v USING (chunk_id) LEFT JOIN b USING (chunk_id)
            WHERE v.chunk_id IS NOT NULL OR b.chunk_id IS NOT NULL
            ORDER BY similarity DESC LIMIT %s"""
        with self.conn.cursor() as cur:
            cur.execute(sql, (self._vec(qvec), self._vec(qvec), k * 2, qtext, qtext, k * 2,
                              vector_weight, bm25_weight, k))
            return [self._row(r) for r in cur.fetchall()]

    @staticmethod
    def _row(r):
        return {"chunk_id": r[0], "paper_id": r[1], "chunk_type": r[2], "section": r[3],
                "content": r[4] or "", "paper_title": r[5] or "", "similarity": float(r[6])}


class MemoryBackend:
    """DB 없이 — 15장의 embedded jsonl 을 통째로 메모리에 올려 코사인 유사도로 찾는다."""

    def __init__(self, files):
        import numpy as np
        self.chunks, vecs = [], []
        for f in files:
            for line in Path(f).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                if c.get("is_reference_section") or not c.get("embedding"):
                    continue                                   # 참고문헌 제외 · 벡터 없는 것 제외
                self.chunks.append(c)
                vecs.append(c["embedding"])
        self.M = np.array(vecs, dtype="float32")             # (N, 1024), 이미 정규화됨

    def vector_search(self, qvec, k=RAG_TOP_K):
        import numpy as np
        q = np.array(qvec, dtype="float32")
        sims = self.M @ q                                      # 정규화됐으니 내적 = 코사인
        idx = np.argsort(-sims)[:k]
        out = []
        for i in idx:
            c = self.chunks[i]
            out.append({"chunk_id": c["chunk_id"], "paper_id": c["paper_id"], "chunk_type": c["chunk_type"],
                        "section": c.get("section", ""), "content": c.get("content_for_llm") or c["content"],
                        "paper_title": (c.get("context_header") or "").split(" | ")[0],
                        "similarity": float(sims[i])})
        return out


# ---------------------------------------------------------------- 두 벌 검색

def merge_two_passes(ko_chunks, en_chunks, weight=HYBRID_WEIGHT):
    """같은 조각이 양쪽에 걸리면 점수를 가중 평균, 한쪽만이면 그쪽 점수. 점수 순."""
    merged = {}
    for c in ko_chunks:
        merged[c["chunk_id"]] = dict(c, similarity=c["similarity"] * weight, hits="ko")
    for c in en_chunks:
        if c["chunk_id"] in merged:
            m = merged[c["chunk_id"]]
            m["similarity"] += c["similarity"] * (1 - weight)
            m["hits"] = "ko+en"
        else:
            merged[c["chunk_id"]] = dict(c, similarity=c["similarity"] * (1 - weight), hits="en")
    return sorted(merged.values(), key=lambda c: c["similarity"], reverse=True)


def retrieve_unified_chunks(question, backend, encoder, k=RAG_TOP_K, en_question=None):
    """한국어 판 + 영어 판 → 합친 후보. en_question 이 없으면 한국어 한 벌만."""
    ko = backend.vector_search(encoder.encode_query(question), k)
    if not en_question or en_question == question:
        return [dict(c, hits="ko") for c in ko]
    en = backend.vector_search(encoder.encode_query(en_question), k)
    return merge_two_passes(ko, en)
