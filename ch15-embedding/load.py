#!/usr/bin/env python3
"""
load.py — 조각과 벡터를 PostgreSQL 에 (15장 "적재와 병목")

    python load.py embedded/PMC000001.embedded.jsonl [more.jsonl ...]
    python load.py embedded/*.jsonl --meta-dir packages/          # papers 행도 함께

한 줄씩 INSERT 하지 않는다. 논문 한 편의 조각을 모아 execute_values 로 한 번에 넣는다.
접속 정보는 환경 변수 PG_DSN (예: postgresql://ai_user:비밀번호@localhost:5432/ai_research_db).

    --dry-run  DB 에 붙지 않고, 보낼 행 수와 첫 행만 보여 준다 (DB 가 없을 때 흐름 확인용)
"""
import argparse
import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

PG_DSN = os.getenv("PG_DSN", "postgresql://ai_user@localhost:5432/ai_research_db")

INSERT_PAPER = """
INSERT INTO papers (paper_id, title, authors, doi, pmid, journal, year, parse_status, parsed_at,
                    figure_count, table_count, chunk_count)
VALUES (%s, %s, %s, %s, %s, %s, %s, 'parsed', now(), %s, %s, %s)
ON CONFLICT (paper_id) DO UPDATE SET
    title = EXCLUDED.title, parse_status = 'parsed', parsed_at = now(),
    figure_count = EXCLUDED.figure_count, table_count = EXCLUDED.table_count, chunk_count = EXCLUDED.chunk_count;
"""

INSERT_CHUNKS = """
INSERT INTO chunks (chunk_id, paper_id, chunk_type, section, context_header, content, content_for_llm,
                    char_count, is_reference_section, figure_id, table_id, table_data, embedding)
VALUES %s
ON CONFLICT (chunk_id) DO UPDATE SET
    content = EXCLUDED.content, content_for_llm = EXCLUDED.content_for_llm,
    context_header = EXCLUDED.context_header, embedding = EXCLUDED.embedding;
"""


def read_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def rows_for(chunks):
    """조각 → execute_values 에 넣을 튜플. 벡터는 '[..]' 문자열로 넘기면 pgvector 가 받는다."""
    out = []
    for c in chunks:
        emb = c.get("embedding")
        out.append((
            c["chunk_id"], c["paper_id"], c["chunk_type"], c.get("section"), c.get("context_header"),
            c["content"], c.get("content_for_llm"), c.get("char_count"),
            bool(c.get("is_reference_section")), c.get("figure_id"), c.get("table_id"),
            json.dumps(c["table_data"], ensure_ascii=False) if c.get("table_data") else None,
            "[" + ",".join(f"{x:.6f}" for x in emb) + "]" if emb else None,
        ))
    return out


def paper_row(meta: dict, chunks):
    n_fig = sum(1 for c in chunks if c["chunk_type"] == "figure_caption")
    n_tab = sum(1 for c in chunks if c["chunk_type"] == "table_data")
    year = meta.get("year")
    return (meta.get("pmcid") or chunks[0]["paper_id"], meta.get("title", ""), meta.get("authors"),
            meta.get("doi"), meta.get("pmid"), meta.get("journal"),
            int(year) if str(year).isdigit() else None, n_fig, n_tab, len(chunks))


def load_file(conn, src: Path, meta_dir: Path | None, dry_run: bool) -> int:
    chunks = read_jsonl(src)
    if not chunks:
        return 0
    paper_id = chunks[0]["paper_id"]
    meta = {}
    if meta_dir and (meta_dir / paper_id / "meta.json").exists():
        meta = json.loads((meta_dir / paper_id / "meta.json").read_text(encoding="utf-8"))
    rows = rows_for(chunks)

    if dry_run:
        print(f"[dry-run] {paper_id}: papers 1행, chunks {len(rows)}행")
        print("          첫 행:", tuple(str(v)[:40] for v in rows[0][:8]), "… embedding[:3]=", rows[0][-1][:24] if rows[0][-1] else None)
        return len(rows)

    from psycopg2.extras import execute_values
    with conn.cursor() as cur:
        cur.execute(INSERT_PAPER, paper_row(meta, chunks))       # 논문 행 먼저 (외래 키)
        execute_values(cur, INSERT_CHUNKS, rows, page_size=200)  # 조각은 한 번에
    conn.commit()
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--meta-dir", type=Path, default=None, help="14장 패키지 폴더 (papers 행을 채우려면)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    conn = None
    if not a.dry_run:
        import psycopg2
        conn = psycopg2.connect(PG_DSN)
    total = 0
    for src in a.inputs:
        total += load_file(conn, src, a.meta_dir, a.dry_run)
    if conn:
        conn.close()
    print(f"총 {total}개 조각{' (dry-run)' if a.dry_run else ' 적재'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
