#!/usr/bin/env python3
"""
common.py — 모든 화면이 함께 쓰는 것: 로그인 문, 사이드바 (18장)

pages/ 의 파일들은 첫 줄에서 require_login() 을 부른다. 로그인이 안 되어 있으면 폼을 보이고 거기서 멈춘다.
세션은 120분 (auth.SESSION_MINUTES). 처음 10분으로 했다가 답을 받다 튕겨 나가서 늘렸다.
"""
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth
from db import init_schema


def _login_page():
    st.title("🌱 산골 RAG — 로그인")
    with st.form("login_form"):
        username = st.text_input("사용자 ID")
        password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인"):
            user = auth.login(username, password)
            if user:
                st.session_state["user"] = user
                st.session_state["login_at"] = time.time()
                st.rerun()
            st.error("로그인 실패. 다섯 번 틀리면 잠깁니다.")


def require_login():
    """로그인된 사용자 dict 를 돌려주거나, 로그인 폼을 보이고 멈춘다."""
    init_schema()
    auth.ensure_admin()
    u = st.session_state.get("user")
    if u and time.time() - st.session_state.get("login_at", 0) < auth.SESSION_MINUTES * 60:
        return u
    st.session_state.pop("user", None)
    _login_page()
    st.stop()


def sidebar_user_info(user):
    with st.sidebar:
        st.markdown(f"**{user.get('full_name') or user['username']}**")
        st.caption(f"역할: {auth.ROLES[user['role']]['name']} (Tier {user['tier']})")
        with st.expander("비밀번호 바꾸기"):
            with st.form("pw_change_form"):
                cur = st.text_input("현재 비밀번호", type="password")
                new = st.text_input("새 비밀번호", type="password")
                if st.form_submit_button("바꾸기"):
                    if auth.change_password(user["username"], cur, new):
                        st.success("바꿨습니다.")
                    else:
                        st.error("현재 비밀번호가 틀립니다.")
        if st.button("로그아웃"):
            st.session_state.pop("user", None)
            st.rerun()
