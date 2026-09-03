#!/usr/bin/env python3
"""
search_internal.py — 사내 데이터를 논문과 같은 방식으로 찾는다 (23장)

    python search_internal.py "층 구조로 안정성을 높이는 방법" --fake
    PG_DSN=... python search_internal.py "질문" --level restricted

두 가지를 보여 준다.

1. **논문 검색과 코드가 같다.** 질문을 벡터로 만들고, 조각의 벡터와 견주고, 가까운 것을 골라 온다.
   16장에서 논문에 쓴 그 연산자, 그 순서다. 새 기술이 없다. 자를 제품과 문서에 대 본 것이다.

2. **등급 밖의 것은 애초에 읽지 않는다.** 표를 직접 읽지 않고 등급으로 걸러진 뷰를 읽는다.
   코드 한 곳에서 실수해도 등급 밖의 것이 나가지 않게 하는 장치다 (schema.sql).

제품 검색도 같은 함수다. 실제 시스템에서는 이것이 모델의 도구로 붙어 있어서,
모델이 필요하다고 판단할 때만 부른다. 늘 나오는 점수는 아무도 보지 않기 때문이다.
"""
import argparse
import os
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

# 등급별로 읽는 뷰. confidential 을 읽는 뷰는 만들지 않았다.
VIEW_BY_LEVEL = {
    "public": "internal.chunks_public",
    "restricted": "internal.chunks_restricted",
}


def encode(text, fake=False):
    if fake:
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        return [(b - 128) / 128 for b in h[:16]]      # 뜻 없는 짧은 벡터
    from sentence_transformers import SentenceTransformer
    global _model
    try:
        _model
    except NameError:
        _model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
                                     device=os.getenv("EMBEDDING_DEVICE", "cpu"))
    return _model.encode(text).tolist()


def _vec(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def search_documents(query, level="restricted", top_k=5):
    """내부문서 검색. 등급으로 걸러진 뷰만 읽는다."""
    view = VIEW_BY_LEVEL.get(level)
    if view is None:
        raise SystemExit(f"'{level}' 등급으로 읽는 뷰는 만들지 않았다. "
                         "필요해지면 그때 만들고, 그때 한 번 더 생각한다 (23장)")
    import psycopg2
    qv = _vec(encode(query))
    sql = f"""
        SELECT c.doc_id, c.chunk_type, c.is_atomic, c.section,
               left(c.content, 300) AS snippet,
               1 - (c.embedding <=> %s::vector) AS similarity
        FROM {view} c
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s"""
    with psycopg2.connect(os.environ["PG_DSN"], connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(sql, (qv, qv, top_k))
        return [{"doc_id": r[0], "chunk_type": r[1], "is_atomic": r[2], "section": r[3],
                 "snippet": r[4], "similarity": float(r[5])} for r in cur.fetchall()]


def search_products(query, top_k=5):
    """제품 검색. 실제 시스템에서는 이것이 모델의 도구로 붙어 있다."""
    import psycopg2
    qv = _vec(encode(query))
    sql = """
        SELECT p.product_id, p.name, left(pc.content, 200) AS snippet,
               1 - (pc.embedding <=> %s::vector) AS similarity
        FROM internal.product_chunks pc
        JOIN internal.products p USING (product_id)
        WHERE pc.embedding IS NOT NULL
        ORDER BY pc.embedding <=> %s::vector
        LIMIT %s"""
    with psycopg2.connect(os.environ["PG_DSN"], connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(sql, (qv, qv, top_k))
        return [{"product_id": r[0], "name": r[1], "snippet": r[2], "similarity": float(r[3])}
                for r in cur.fetchall()]


# ---------------------------------------------------------------- 연습 모드

FAKE_DOCS = [
    {"doc_id": "DOC-A", "chunk_type": "claim", "is_atomic": True, "section": "청구항 1",
     "snippet": "(연습용) 제1 층과 제2 층이 접촉 면적을 제한하도록 배치되는 조성물",
     "sensitivity": "public"},
    {"doc_id": "DOC-A", "chunk_type": "text", "is_atomic": False, "section": "과제의 해결 수단",
     "snippet": "(연습용) 두 성분이 서로 접촉하는 면적을 최소화하여 상호작용을 억제한다",
     "sensitivity": "public"},
    {"doc_id": "DOC-B", "chunk_type": "text", "is_atomic": False, "section": "실험 기록",
     "snippet": "(연습용) 아직 출원하지 않은 조건 탐색 기록",
     "sensitivity": "confidential"},
    {"doc_id": "DOC-C", "chunk_type": "table", "is_atomic": False, "section": "표 2",
     "snippet": "(연습용) 사내 열람용 안정성 시험 요약표",
     "sensitivity": "restricted"},
]
ALLOWED = {"public": {"public"}, "restricted": {"public", "restricted"}}


def fake_search(query, level, top_k=5):
    allow = ALLOWED.get(level)
    if allow is None:
        raise SystemExit(f"'{level}' 등급으로 읽는 뷰는 만들지 않았다 (23장)")
    hidden = [d for d in FAKE_DOCS if d["sensitivity"] not in allow]
    shown = [d for d in FAKE_DOCS if d["sensitivity"] in allow][:top_k]
    return shown, hidden


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--level", default="restricted", choices=["public", "restricted", "confidential"])
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--fake", action="store_true", help="DB 없이 등급 걸러내기만 보여 준다")
    ap.add_argument("--products", action="store_true", help="제품도 함께 찾는다")
    a = ap.parse_args()

    if a.fake:
        shown, hidden = fake_search(a.query, a.level, a.top_k)
        print(f"질문: {a.query}")
        print(f"등급: {a.level}  →  뷰 {VIEW_BY_LEVEL.get(a.level, '(없음)')}")
        print()
        for d in shown:
            mark = "[통째]" if d["is_atomic"] else "      "
            print(f"{mark} {d['doc_id']} · {d['section']:<14} ({d['sensitivity']})")
            print(f"        {d['snippet']}")
        print()
        print(f"등급 밖이라 애초에 읽지 않은 조각: {len(hidden)}개")
        for d in hidden:
            print(f"        {d['doc_id']} ({d['sensitivity']}) — 목록에도 나타나지 않는다")
        print()
        print("걸러 낸 것이 아니라 읽지 않은 것이다. 뷰가 등급 밖을 아예 담고 있지 않다.")
        return 0

    rows = search_documents(a.query, a.level, a.top_k)
    print(f"내부문서 {len(rows)}건")
    for r in rows:
        mark = "[통째]" if r["is_atomic"] else "      "
        print(f"{mark} {r['similarity']:.3f} {r['doc_id']} · {r['section']}")
        print(f"        {r['snippet'][:120]}")
    if a.products:
        pr = search_products(a.query, a.top_k)
        print(f"\n제품 {len(pr)}건")
        for r in pr:
            print(f"  {r['similarity']:.3f} {r['product_id']} · {r['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
