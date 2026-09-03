#!/usr/bin/env python3
"""pages/9_용어_관리.py — LLM 이 쓴 해설을 사람이 확정한다 (18장 "용어사전이 자란다")"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import require_login, sidebar_user_info   # noqa: E402
import auth, glossary                              # noqa: E402

user = require_login()
sidebar_user_info(user)
st.title("📖 용어 관리")

status = st.radio("보기", ["pending", "approved", "rejected"], horizontal=True)
terms = glossary.list_terms(status=status)
st.caption(f"{status}: {len(terms)}개")
can_review = auth.has_permission(user["role"], "export")     # 핵심 연구원부터 검토

for t in terms:
    with st.expander(f"{t['term_en']}  ·  사용 {t['usage_count']}회  ·  {t['source_page']}"):
        new_def = st.text_area("해설", t["definition_ko"] or "", key=f"def_{t['id']}")
        st.caption(f"출처 논문: {t['source_pmcids'] or '-'} · 쓴 화면: {t['used_by_pages']}")
        if can_review:
            c1, c2 = st.columns(2)
            if c1.button("승인", key=f"ok_{t['id']}"):
                glossary.review_term(t["id"], user["username"], "approved", new_def); st.rerun()
            if c2.button("반려", key=f"no_{t['id']}"):
                glossary.review_term(t["id"], user["username"], "rejected"); st.rerun()
