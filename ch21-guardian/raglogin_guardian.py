#!/usr/bin/env python3
"""
raglogin_guardian.py — 앱에 누가 로그인했는가 (21장)

    python raglogin_guardian.py           실제 DB (PG_DSN 필요)
    python raglogin_guardian.py --demo    DB 없이 규칙만

18장에서 만든 users 표의 세 칸을 읽는다.
    last_login      바뀌면 → 로그인
    login_failures  늘면   → 실패 시도
    is_active       꺼지면 → 계정 잠금

여기서 가장 중요한 줄도 알림을 보내는 줄이 아니다.
처음 보는 사용자를 건너뛰는 줄이다. 비교할 어제가 없을 때는 말하지 않는다.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import load_state, save_state, send   # noqa: E402


def fetch_users():
    """(username, role, last_login, login_failures, is_active) 목록."""
    import psycopg2
    dsn = os.getenv("PG_DSN")
    if not dsn:
        raise SystemExit("PG_DSN 이 필요하다.  export PG_DSN=postgresql://user:pw@host:5432/db")
    with psycopg2.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT username, role, last_login, login_failures, is_active FROM users")
        return cur.fetchall()


def compare(prev, rows):
    """지난번과 견줘 세 가지를 골라낸다."""
    now, logins, fails, locks = {}, [], [], []
    for username, role, last_login, nfail, active in rows:
        ll = last_login.strftime("%m-%d %H:%M") if last_login else None
        now[username] = {"ll": ll, "f": nfail or 0, "a": bool(active)}
        p = prev.get(username)
        if not p:
            continue          # ★ 처음 보는 사용자는 건너뛴다 (첫 실행에 열아홉 통이 가지 않게)
        if ll and ll != p.get("ll"):
            logins.append(f"{username} ({role})\n시각: {ll}")
        if (nfail or 0) > p.get("f", 0):
            fails.append(f"{username}: 실패 {p.get('f', 0)} → {nfail}회")
        if p.get("a") and not active:
            locks.append(f"{username} — 실패 누적으로 잠김")
    return now, logins, fails, locks


def report(logins, fails, locks):
    if logins:
        send("🔓 앱 로그인\n\n" + "\n\n".join(logins))
    if fails:
        send("⚠️ 로그인 실패 시도\n\n" + "\n".join(fails))
    if locks:
        send("🔒 계정 잠금\n\n" + "\n".join(locks))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        _demo()
        return 0

    prev = load_state("raglogin")
    now, logins, fails, locks = compare(prev, fetch_users())
    report(logins, fails, locks)
    save_state("raglogin", now)
    print(f"사용자 {len(now)}명 | 로그인 {len(logins)} | 실패 {len(fails)} | 잠금 {len(locks)}")
    return 0


def _demo():
    import datetime
    t1 = datetime.datetime(2026, 9, 3, 9, 12)
    t2 = datetime.datetime(2026, 9, 3, 14, 30)

    print("=== 1회차 — 처음 본 사용자 셋 ==================================")
    rows = [("kim", "researcher", t1, 0, True), ("lee", "core", None, 0, True), ("park", "admin", t1, 0, True)]
    prev, (now, lo, fa, lk) = {}, compare({}, rows)
    print(f"  로그인 {len(lo)} · 실패 {len(fa)} · 잠금 {len(lk)}  → 알림 없음 (비교할 어제가 없다)")

    print("\n=== 2회차 — kim 이 다시 로그인, park 은 비밀번호를 틀렸다 =========")
    prev = now
    rows = [("kim", "researcher", t2, 0, True), ("lee", "core", None, 0, True), ("park", "admin", t1, 3, True)]
    now, lo, fa, lk = compare(prev, rows)
    report(lo, fa, lk)

    print("\n=== 3회차 — park 이 다섯 번 틀려 계정이 잠겼다 ====================")
    prev = now
    rows = [("kim", "researcher", t2, 0, True), ("lee", "core", None, 0, True), ("park", "admin", t1, 5, False)]
    now, lo, fa, lk = compare(prev, rows)
    report(lo, fa, lk)
    print("\n세 번 돌아 알림 넷. 아무 일 없는 사용자에 대해서는 한 번도 말하지 않았다.")


if __name__ == "__main__":
    sys.exit(main())
