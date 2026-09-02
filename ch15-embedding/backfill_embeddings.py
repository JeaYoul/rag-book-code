#!/usr/bin/env python3
"""
backfill_embeddings.py — 벡터가 비어 있는 조각만 골라 채운다 (15장 "두 단계로 나눈다")

    python backfill_embeddings.py [--limit N] [--fake]

이 스크립트가 곧 체크포인트다. embedding IS NULL 인 행이 "아직 안 한 것" 이니,
어디까지 했는지 따로 적을 필요가 없다. 죽으면 그냥 다시 돌린다.
실제 embedding.py 와 같은 값: 인코딩 배치 32, 커밋 256.
"""
import argparse
import os
import sys

from embed import ENCODE_BATCH, Encoder

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

PG_DSN = os.getenv("PG_DSN", "postgresql://ai_user@localhost:5432/ai_research_db")
COMMIT_BATCH = 256


def fetch_chunks_without_embedding(conn, limit=None):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_id, content FROM chunks WHERE embedding IS NULL ORDER BY chunk_id"
            + (f" LIMIT {int(limit)}" if limit else "")
        )
        return cur.fetchall()


def update_embeddings(conn, ids, vecs):
    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        execute_values(cur,
            "UPDATE chunks AS c SET embedding = v.emb::vector FROM (VALUES %s) AS v(chunk_id, emb) "
            "WHERE c.chunk_id = v.chunk_id",
            [(cid, "[" + ",".join(f"{x:.6f}" for x in v) + "]") for cid, v in zip(ids, vecs)],
        )


def run(limit=None, fake=False) -> int:
    import psycopg2
    conn = psycopg2.connect(PG_DSN)
    todo = fetch_chunks_without_embedding(conn, limit)
    print(f"벡터가 빈 조각: {len(todo)}개")
    if not todo:
        return 0
    enc = Encoder(fake=fake)
    done = 0
    for start in range(0, len(todo), ENCODE_BATCH):                 # 32개씩
        batch = todo[start:start + ENCODE_BATCH]
        vecs = enc.encode([content for _, content in batch])
        update_embeddings(conn, [cid for cid, _ in batch], vecs)
        done += len(batch)
        if done % COMMIT_BATCH == 0:                                 # 256개마다 커밋
            conn.commit()
            print(f"  {done}/{len(todo)}")
    conn.commit()
    conn.close()
    print(f"채움: {done}개")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--fake", action="store_true", help="모델 없이 가짜 벡터 (실습·테스트용)")
    a = ap.parse_args()
    return run(a.limit, a.fake)


if __name__ == "__main__":
    sys.exit(main())
