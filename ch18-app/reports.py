#!/usr/bin/env python3
"""
reports.py — 보고서가 쌓인다 (18장)

답이 나오면 일단 user_reports 에 넣어 두고(is_saved=false),
연구자가 저장 버튼을 누르면 표시를 켠다(is_saved=true). 파일은 만들지 않는다.
저장 안 한 것은 나중에 지운다. "내 보고서" 에서 다시 열면 그림 번호까지 그대로다.
"""
from db import cursor, fetchall_dicts, is_pg, q


def _list(v):
    return list(v) if isinstance(v, (list, tuple)) else [x for x in (v or "").split(",") if x]


def _store(v):
    return list(v) if is_pg() else ",".join(v)


def save_report(username, question, answer, figure_ids=(), table_ids=(), chembl_summary=None):
    """답이 나온 직후 — 임시로 넣는다. 돌려주는 값은 report_id."""
    with cursor() as cur:
        if is_pg():
            cur.execute("INSERT INTO user_reports (username, question, answer, figure_ids, table_ids, chembl_summary) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING report_id",
                        (username, question, answer, list(figure_ids), list(table_ids), chembl_summary))
            return cur.fetchone()[0]
        cur.execute(q("INSERT INTO user_reports (username, question, answer, figure_ids, table_ids, chembl_summary) "
                      "VALUES (%s, %s, %s, %s, %s, %s)"),
                    (username, question, answer, ",".join(figure_ids), ",".join(table_ids), chembl_summary))
        return cur.lastrowid


def mark_saved(report_id):
    """저장 버튼 — 새로 만들지 않고 표시만 켠다."""
    with cursor() as cur:
        cur.execute(q("UPDATE user_reports SET is_saved = %s, updated_at = CURRENT_TIMESTAMP WHERE report_id = %s"),
                    (True if is_pg() else 1, report_id))


def list_reports(username, only_saved=True, limit=50):
    with cursor(commit=False) as cur:
        sql = "SELECT report_id, question, is_saved, created_at FROM user_reports WHERE username = %s"
        if only_saved:
            sql += " AND is_saved = " + ("true" if is_pg() else "1")
        cur.execute(q(sql + " ORDER BY created_at DESC LIMIT %s"), (username, limit))
        return fetchall_dicts(cur)


def load_report(report_id):
    with cursor(commit=False) as cur:
        cur.execute(q("SELECT * FROM user_reports WHERE report_id = %s"), (report_id,))
        rows = fetchall_dicts(cur)
    if not rows:
        return None
    r = rows[0]
    r["figure_ids"], r["table_ids"] = _list(r["figure_ids"]), _list(r["table_ids"])
    return r


def purge_unsaved(older_than_days=7):
    """저장 안 한 임시 보고서는 지운다."""
    with cursor() as cur:
        if is_pg():
            cur.execute("DELETE FROM user_reports WHERE NOT is_saved AND created_at < now() - (%s || ' days')::interval",
                        (str(older_than_days),))
        else:
            cur.execute("DELETE FROM user_reports WHERE is_saved = 0 AND created_at < datetime('now', ?)",
                        (f"-{older_than_days} days",))
        return cur.rowcount
