#!/usr/bin/env python3
"""
Home.py — 첫 화면: 로그인, 대시보드, 관리자의 사용자 만들기 (18장)

    streamlit run Home.py --server.port 8501

pages/ 폴더의 파일이 왼쪽 메뉴가 된다. 모든 화면은 common.require_login() 뒤에만 열린다.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth
from common import require_login, sidebar_user_info
from db import cursor

st.set_page_config(page_title="산골 RAG", page_icon="🌱", layout="wide")
user = require_login()
sidebar_user_info(user)


def stats():
    with cursor(commit=False) as cur:
        out = {}
        for name, sql in (("사용자", "SELECT count(*) FROM users"), ("보고서", "SELECT count(*) FROM user_reports"),
                          ("용어", "SELECT count(*) FROM glossary_terms"), ("대화", "SELECT count(*) FROM chat_logs")):
            cur.execute(sql)
            out[name] = cur.fetchone()[0]
    return out


st.title("🌱 산골 RAG")
for col, (k, v) in zip(st.columns(4), stats().items()):
    col.metric(k, v)
st.markdown("왼쪽 메뉴에서 화면을 고르세요. **논문 검색**에서 시작합니다.")

if auth.has_permission(user["role"], "user_manage"):
    st.subheader("사용자 만들기 (관리자)")
    with st.form("new_user"):
        c1, c2, c3 = st.columns(3)
        nu = c1.text_input("ID")
        npw = c2.text_input("비밀번호", type="password")
        nrole = c3.selectbox("역할", list(auth.ROLES))
        if st.form_submit_button("만들기") and nu and npw:
            auth.create_user(user["username"], nu, npw, nrole)
            st.success(f"{nu} ({auth.ROLES[nrole]['name']}) 만들었습니다. 감사 로그에 남았습니다.")
