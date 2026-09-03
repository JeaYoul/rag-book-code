#!/usr/bin/env python3
"""
pages/1_논문_검색.py — 이 장의 주인공 (18장 "검색 UI")

질문 한 줄 → 16장 검색 → 12장 LLM → 답 + [n] 인용 + 참고문헌 → 용어 해설 → 저장 버튼 → 문서 4종.
검색 백엔드는 환경 변수로 고른다:
    PG_DSN 있음            실제 pgvector
    MEMORY_CORPUS=*.jsonl  15장의 가짜 코퍼스 (실습)
"""
import glob
import os
import sys
import time
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "ch16-retrieval")); sys.path.insert(0, str(HERE.parent / "ch15-embedding"))
from common import require_login, sidebar_user_info          # noqa: E402  (로그인 게이트)
import auth, exporter, glossary, reports                  # noqa: E402
from db import cursor, q                                  # noqa: E402

user = require_login()
sidebar_user_info(user)
st.title("📚 논문 검색")

FAKE = not os.getenv("PG_DSN")


@st.cache_resource
def backend_and_encoder():
    from embed import Encoder
    if os.getenv("PG_DSN"):
        from search import PgBackend
        return PgBackend(), Encoder(fake=False)
    from search import MemoryBackend
    files = glob.glob(os.getenv("MEMORY_CORPUS", str(HERE.parent / "ch15-embedding" / "embedded" / "*.jsonl")))
    return MemoryBackend(files), Encoder(fake=True)


with st.sidebar:
    top_k = st.slider("📊 검색 논문 수", 5, 50, 20)
    mode = st.radio("모드", ["빠른 답", "깊은 답"], horizontal=True)

with st.form("search_form"):
    question = st.text_input("💬 질문", placeholder="예: 설포라판의 항암 효과와 Nrf2 활성화 메커니즘은?")
    go = st.form_submit_button("검색")

if go and question.strip():
    from pipeline import ask_llm, build_context, enhanced_search
    from rerank import FakeReranker
    backend, encoder = backend_and_encoder()
    t0 = time.time()
    ctx_terms = glossary.term_context(question)                          # 사전이 아는 말은 맥락으로
    res = enhanced_search(question, backend, encoder, top_k=5 if mode == "빠른 답" else 10,
                          use_llm=not FAKE, reranker=FakeReranker() if FAKE else None)
    t_search = time.time() - t0
    context = (f"[용어]\n{ctx_terms}\n\n" if ctx_terms else "") + build_context(res["merged_chunks"])
    t1 = time.time()
    if FAKE:
        answer = "\n\n".join(f"{c['content'][:200]} [{i+1}]" for i, c in enumerate(res["merged_chunks"][:3])) or "근거 없음"
    else:
        answer = ask_llm(context, question, max_tokens=2048 if mode == "빠른 답" else 4096)
    t_llm = time.time() - t1

    pmcids = [c["paper_id"] for c in res["merged_chunks"]]
    answer += glossary.build_glossary(answer, "1_논문_검색", source_pmcids=pmcids)   # 용어사전이 자란다
    st.markdown(answer)
    st.subheader("참고문헌")
    for i, c in enumerate(res["merged_chunks"], 1):
        st.markdown(f"[{i}] **{c.get('paper_title') or c['paper_id']}** — {c.get('section', '')} · `{c['paper_id']}`")

    rid = reports.save_report(user["username"], question, answer)          # 일단 넣어 두고
    with cursor() as cur:
        cur.execute(q("INSERT INTO chat_logs (username, query_text, response_text, mode, search_sec, llm_sec) VALUES (%s, %s, %s, %s, %s, %s)"),
                    (user["username"], question, answer[:2000], mode, round(t_search, 2), round(t_llm, 2)))
    st.session_state["last"] = {"rid": rid, "question": question, "answer": answer}
    st.caption(f"검색 {t_search:.1f}s · 답 {t_llm:.1f}s · 근거 {len(res['merged_chunks'])}조각 · 논문 {res['unique_papers']}편")

if last := st.session_state.get("last"):
    c1, c2 = st.columns([1, 3])
    if c1.button("💾 이 답을 보고서로 저장"):
        reports.mark_saved(last["rid"])                                     # 표시만 켠다 — 파일 없음
        st.success("저장했습니다. '내 보고서'에서 다시 열 수 있습니다.")
    if auth.has_permission(user["role"], "export"):
        markup = exporter.answer_to_markup(last["question"][:60], last["answer"])
        cols = c2.columns(4)
        for col, fmt in zip(cols, ("html", "docx", "pptx", "pdf")):
            r = exporter.export(markup, fmt)
            if r.data:
                col.download_button(f"{fmt.upper()} 내려받기", r.data, file_name=f"report.{fmt}", mime=r.mime)
            else:
                col.caption(f"{fmt}: " + "; ".join(r.warnings))
    else:
        c2.caption("문서 출력은 핵심 연구원부터 할 수 있습니다.")

st.divider()
st.subheader("내 보고서")
for r in reports.list_reports(user["username"], only_saved=True, limit=20):
    if st.button(f"열기 · {r['question'][:60]}  ({str(r['created_at'])[:10]})", key=f"open_{r['report_id']}"):
        rep = reports.load_report(r["report_id"])
        st.markdown(rep["answer"])
