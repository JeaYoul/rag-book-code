#!/usr/bin/env python3
"""
db.py — 앱이 쓰는 데이터베이스 연결 (18장)

PG_DSN 이 있으면 PostgreSQL, 없으면 같은 폴더의 app.sqlite 로 돈다 (실습용).
SQL 은 PostgreSQL 식(%s)으로 쓰고, SQLite 일 때만 ? 로 바꿔 준다.
테이블 넷: users · login_attempts · admin_actions · user_reports · glossary_terms · chat_logs
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PG_DSN = os.getenv("PG_DSN")
SQLITE_PATH = Path(os.getenv("APP_SQLITE", Path(__file__).with_name("app.sqlite")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        {serial},
    username       VARCHAR(50) UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    role           VARCHAR(20) DEFAULT 'researcher',
    full_name      TEXT, dept TEXT,
    is_active      BOOLEAN DEFAULT {true},
    login_failures INTEGER DEFAULT 0,
    last_login     TIMESTAMP,
    created_at     TIMESTAMP DEFAULT {now}
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id {serial}, username VARCHAR(100), success BOOLEAN, reason TEXT, source_app TEXT, client_ip TEXT,
    attempted_at TIMESTAMP DEFAULT {now}
);
CREATE TABLE IF NOT EXISTS admin_actions (
    id {serial}, actor VARCHAR(100), action TEXT, target TEXT, detail TEXT, acted_at TIMESTAMP DEFAULT {now}
);
CREATE TABLE IF NOT EXISTS user_reports (
    report_id {serial}, username VARCHAR(100) NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
    figure_ids TEXT DEFAULT '', table_ids TEXT DEFAULT '', chembl_summary TEXT,
    is_saved BOOLEAN DEFAULT {false}, created_at TIMESTAMP DEFAULT {now}, updated_at TIMESTAMP DEFAULT {now}
);
CREATE TABLE IF NOT EXISTS glossary_terms (
    id {serial}, term_en VARCHAR(200) UNIQUE NOT NULL, term_ko VARCHAR(200), definition_ko TEXT, definition_en TEXT,
    category VARCHAR(100), source_pmcids TEXT DEFAULT '', source_page VARCHAR(50) NOT NULL, used_by_pages TEXT DEFAULT '',
    usage_count INTEGER DEFAULT 1, review_status VARCHAR(20) DEFAULT 'pending', reviewed_by VARCHAR(100), reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT {now}, updated_at TIMESTAMP DEFAULT {now}
);
CREATE TABLE IF NOT EXISTS chat_logs (
    id {serial}, username VARCHAR(100), query_text TEXT, response_text TEXT, mode VARCHAR(20),
    search_sec REAL, llm_sec REAL, created_at TIMESTAMP DEFAULT {now}
);
"""


def is_pg() -> bool:
    return bool(PG_DSN)


def _connect():
    if is_pg():
        import psycopg2
        return psycopg2.connect(PG_DSN)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql: str) -> str:
    """PostgreSQL 식 자리표시자(%s)를 SQLite 용(?)으로."""
    return sql if is_pg() else sql.replace("%s", "?")


@contextmanager
def cursor(commit=True):
    conn = _connect()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def fetchall_dicts(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def init_schema():
    if is_pg():
        s = SCHEMA.format(serial="SERIAL PRIMARY KEY", now="now()", true="true", false="false")
    else:
        s = SCHEMA.format(serial="INTEGER PRIMARY KEY AUTOINCREMENT", now="CURRENT_TIMESTAMP", true="1", false="0")
    with cursor() as cur:
        for stmt in [x.strip() for x in s.split(";") if x.strip()]:
            cur.execute(stmt)
