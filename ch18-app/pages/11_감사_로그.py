#!/usr/bin/env python3
"""pages/11_감사_로그.py — 누가 언제 무엇을 했나 (18장 "관리자 인증")"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import require_login, sidebar_user_info   # noqa: E402
import auth                                        # noqa: E402
from db import cursor, fetchall_dicts              # noqa: E402

user = require_login()
sidebar_user_info(user)
st.title("🧾 감사 로그")
if not auth.has_permission(user["role"], "admin"):
    st.warning("관리자만 볼 수 있습니다."); st.stop()

with cursor(commit=False) as cur:
    cur.execute("SELECT username, success, reason, source_app, client_ip, attempted_at FROM login_attempts ORDER BY attempted_at DESC LIMIT 200")
    logins = fetchall_dicts(cur)
    cur.execute("SELECT actor, action, target, detail, acted_at FROM admin_actions ORDER BY acted_at DESC LIMIT 200")
    actions = fetchall_dicts(cur)

st.subheader("로그인 시도"); st.dataframe(logins, use_container_width=True)
st.subheader("관리자 행위"); st.dataframe(actions, use_container_width=True)
locked = [l["username"] for l in logins if l["reason"] == "locked"]
if locked:
    st.warning(f"잠긴 계정 시도: {sorted(set(locked))}")
    name = st.selectbox("잠금 풀기", sorted(set(locked)))
    if st.button("풀기"):
        auth.unlock_user(user["username"], name); st.success(f"{name} 잠금을 풀었습니다."); st.rerun()
