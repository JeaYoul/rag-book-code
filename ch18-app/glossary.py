#!/usr/bin/env python3
"""
glossary.py — 용어사전이 자란다 (18장)

    lookup_term      사전에 있는가
    increment_usage  있으면 꺼내 쓰고 사용 횟수 +1, 어느 화면이 썼는지 기록
    register_term    없으면 (LLM 이 쓴 해설을) 새로 등록 — 검토 상태는 pending
    build_glossary   답에서 용어 후보를 뽑아 위 셋을 돌리고, 답 끝에 붙일 해설 절을 만든다
    term_context     질문에 사전 용어가 보이면 그 정의를 검색 프롬프트의 맥락으로

LLM 이 없으면(--fake) 해설 자리에 "(해설 미작성 — 검토 필요)" 를 넣어 등록만 한다.
"""
import os
import re

from db import cursor, fetchall_dicts, is_pg, q

TERM_RE = re.compile(r"\b([A-Z][A-Za-z0-9\-]{2,}|[A-Za-z]+-CoA|Nrf2|HDAC\d?|NF-κB|SCFA[s]?)\b")


def _arr(v):
    return list(v) if isinstance(v, (list, tuple)) else [x for x in (v or "").split(",") if x]


def _store(v):
    return list(v) if is_pg() else ",".join(v)


def lookup_term(term_en):
    with cursor(commit=False) as cur:
        cur.execute(q("SELECT * FROM glossary_terms WHERE lower(term_en) = lower(%s)"), (term_en,))
        rows = fetchall_dicts(cur)
    return rows[0] if rows else None


def increment_usage(term_en, page_name):
    row = lookup_term(term_en)
    if not row:
        return
    pages = _arr(row["used_by_pages"])
    if page_name not in pages:
        pages.append(page_name)
    with cursor() as cur:
        cur.execute(q("UPDATE glossary_terms SET usage_count = usage_count + 1, used_by_pages = %s, "
                      "updated_at = CURRENT_TIMESTAMP WHERE id = %s"), (_store(pages), row["id"]))


def register_term(term_en, definition_ko, source_page, term_ko=None, category=None, source_pmcids=()):
    with cursor() as cur:
        cur.execute(q("INSERT INTO glossary_terms (term_en, term_ko, definition_ko, category, source_pmcids, source_page, used_by_pages) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s)"),
                    (term_en, term_ko, definition_ko, category, _store(list(source_pmcids)), source_page, _store([source_page])))


def review_term(term_id, reviewer, status="approved", definition_ko=None):
    with cursor() as cur:
        if definition_ko is not None:
            cur.execute(q("UPDATE glossary_terms SET definition_ko = %s WHERE id = %s"), (definition_ko, term_id))
        cur.execute(q("UPDATE glossary_terms SET review_status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP WHERE id = %s"),
                    (status, reviewer, term_id))


def list_terms(status=None, limit=100):
    with cursor(commit=False) as cur:
        if status:
            cur.execute(q("SELECT * FROM glossary_terms WHERE review_status = %s ORDER BY usage_count DESC LIMIT %s"), (status, limit))
        else:
            cur.execute(q("SELECT * FROM glossary_terms ORDER BY usage_count DESC LIMIT %s"), (limit,))
        return fetchall_dicts(cur)


def extract_term_candidates(text, max_terms=8):
    seen, out = set(), []
    for m in TERM_RE.finditer(re.sub(r"\[[^\]]*\]", "", text)):
        t = m.group(1)
        if t.lower() not in seen and t.upper() != t or t in ("HDAC", "SCFA", "SCFAs"):
            seen.add(t.lower())
            out.append(t)
        if len(out) >= max_terms:
            break
    return out


def define_with_llm(terms):
    """없는 용어의 해설을 LLM 에게. 연결이 안 되면 자리만 채운다."""
    base = os.getenv("LLM_BASE_URL")
    if not base or not terms:
        return {t: "(해설 미작성 — 검토 필요)" for t in terms}
    try:
        import requests
        prompt = "다음 생의학 용어를 각각 한 줄(40자 이내)로 쉬운 한국어로 설명하라. 형식: 용어: 설명\n" + "\n".join(terms)
        r = requests.post(f"{base}/chat/completions", json={
            "model": os.getenv("LLM_MODEL", "qwen"), "temperature": 0.2, "max_tokens": 600,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": prompt}]}, timeout=60)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or ""
        out = {}
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip("-• ").strip()] = v.strip()
        return {t: out.get(t, "(해설 미작성 — 검토 필요)") for t in terms}
    except Exception:
        return {t: "(해설 미작성 — 검토 필요)" for t in terms}


def build_glossary(answer_text, page_name, source_pmcids=()):
    """있으면 꺼내 쓰고 +1, 없으면 만들어 등록. 답 끝에 붙일 절을 돌려준다."""
    terms = extract_term_candidates(answer_text)
    known, unknown = [], []
    for t in terms:
        hit = lookup_term(t)
        if hit:
            increment_usage(t, page_name)
            known.append((t, hit["definition_ko"]))
        else:
            unknown.append(t)
    fresh = define_with_llm(unknown)
    for t, d in fresh.items():
        register_term(t, d, page_name, source_pmcids=source_pmcids)
    items = known + list(fresh.items())
    if not items:
        return ""
    return "\n\n---\n**용어 해설**\n" + "\n".join(f"- **{t}** — {d}" for t, d in items)


def term_context(question):
    """질문에 사전 용어가 보이면 그 정의를 검색 맥락으로."""
    hits = [lookup_term(t) for t in extract_term_candidates(question)]
    hits = [h for h in hits if h]
    return "\n".join(f"{h['term_en']}: {h['definition_ko']}" for h in hits)
