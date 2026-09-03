#!/usr/bin/env python3
"""
auth.py — 인증과 권한 (18장 "관리자 인증")

    역할 셋 (실제 시스템과 같은 3-Tier)
      researcher  Tier 1  검색, 답 보기, 자기 이력
      core        Tier 2  + 문서 출력, 논문 올리기, 과학 도구(19장)
      admin       Tier 3  + 사용자 관리, 시스템 설정, DB 조회, 통계

    비밀번호는 bcrypt 해시 (bcrypt 가 없으면 sha256 — 실습용). 다섯 번 틀리면 잠근다.
    로그인 시도는 성공이든 실패든 전부 login_attempts 에, 관리자 행위는 admin_actions 에 남긴다.
"""
import hashlib
import os
from datetime import datetime

from db import cursor, fetchall_dicts, q

ROLES = {
    "admin":      {"name": "CEO/관리자", "tier": 3, "permissions": ["search", "export", "bionemo", "upload", "admin", "user_manage"]},
    "core":       {"name": "핵심 연구원", "tier": 2, "permissions": ["search", "export", "bionemo", "upload"]},
    "researcher": {"name": "일반 연구원", "tier": 1, "permissions": ["search"]},
}
MAX_LOGIN_FAILURES = 5
SESSION_MINUTES = 120                       # 10분에서 120분으로 — 답 하나에 1분 걸리는 시스템이라
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin_change_me_immediately")


def get_tier(role):
    return ROLES.get(role, ROLES["researcher"])["tier"]


def has_permission(role, perm):
    return perm in ROLES.get(role, ROLES["researcher"])["permissions"]


# ---------------------------------------------------------------- 비밀번호

def hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:                                           # 실습용 물러섬 — 운영에서는 쓰지 마라
        return "sha256$" + hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("sha256$"):
        return hashed == "sha256$" + hashlib.sha256(password.encode()).hexdigest()
    import bcrypt
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------------------------------------------------------------- 사용자

def ensure_admin():
    """admin 계정이 없을 때만 만든다. 있으면 비밀번호를 덮어쓰지 않는다."""
    with cursor() as cur:
        cur.execute(q("SELECT user_id FROM users WHERE username = %s"), ("admin",))
        if cur.fetchone() is None:
            cur.execute(q("INSERT INTO users (username, password_hash, role, full_name) VALUES (%s, %s, 'admin', %s)"),
                        ("admin", hash_password(DEFAULT_ADMIN_PASSWORD), "관리자"))


def create_user(actor, username, password, role="researcher", full_name=None, dept=None):
    with cursor() as cur:
        cur.execute(q("INSERT INTO users (username, password_hash, role, full_name, dept) VALUES (%s, %s, %s, %s, %s)"),
                    (username, hash_password(password), role, full_name, dept))
    log_admin_action(actor, "create_user", username, f"role={role}")


def get_user(username):
    with cursor(commit=False) as cur:
        cur.execute(q("SELECT * FROM users WHERE username = %s"), (username,))
        rows = fetchall_dicts(cur)
    return rows[0] if rows else None


def log_login_attempt(username, success, reason=None, source_app="Home", client_ip=None):
    with cursor() as cur:
        cur.execute(q("INSERT INTO login_attempts (username, success, reason, source_app, client_ip) VALUES (%s, %s, %s, %s, %s)"),
                    (username, success, reason, source_app, client_ip))


def log_admin_action(actor, action, target=None, detail=None):
    with cursor() as cur:
        cur.execute(q("INSERT INTO admin_actions (actor, action, target, detail) VALUES (%s, %s, %s, %s)"),
                    (actor, action, target, detail))


def login(username, password, client_ip=None):
    """성공하면 사용자 dict, 실패하면 None. 다섯 번 틀리면 잠근다."""
    user = get_user(username)
    if not user:
        log_login_attempt(username, False, "no_such_user", client_ip=client_ip)
        return None
    if not user["is_active"]:
        log_login_attempt(username, False, "inactive", client_ip=client_ip)
        return None
    if user["login_failures"] >= MAX_LOGIN_FAILURES:
        log_login_attempt(username, False, "locked", client_ip=client_ip)
        return None
    if not verify_password(password, user["password_hash"]):
        with cursor() as cur:
            cur.execute(q("UPDATE users SET login_failures = login_failures + 1 WHERE username = %s"), (username,))
        log_login_attempt(username, False, "bad_password", client_ip=client_ip)
        return None
    with cursor() as cur:
        cur.execute(q("UPDATE users SET login_failures = 0, last_login = %s WHERE username = %s"),
                    (datetime.now(), username))
    log_login_attempt(username, True, client_ip=client_ip)
    role = user["role"] if user["role"] in ROLES else "researcher"
    return {"username": username, "role": role, "tier": get_tier(role),
            "permissions": ROLES[role]["permissions"], "full_name": user.get("full_name")}


def unlock_user(actor, username):
    with cursor() as cur:
        cur.execute(q("UPDATE users SET login_failures = 0 WHERE username = %s"), (username,))
    log_admin_action(actor, "unlock_user", username)


def change_password(username, current, new):
    user = get_user(username)
    if not user or not verify_password(current, user["password_hash"]):
        return False
    with cursor() as cur:
        cur.execute(q("UPDATE users SET password_hash = %s WHERE username = %s"), (hash_password(new), username))
    return True
