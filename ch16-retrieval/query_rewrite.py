#!/usr/bin/env python3
"""
query_rewrite.py — 질문을 세 겹으로 다듬는다 (16장 "쿼리 리라이팅")

    ① 옮긴다   translate_to_english   용어표 먼저, 남으면 LLM (없으면 용어표까지만)
    ② 넓힌다   expand_with_synonyms   동의어 사전 — 정식 화학명·공식 약어만. 원료명은 뺐다 (희석)
    ③ 쪼갠다   is_complex_query / decompose_query   다섯 신호 중 둘 이상이면 서브쿼리 2~6개

    python query_rewrite.py "설포라판의 Nrf2 경로와 HDAC 억제, 그리고 면역 조절 기전을 설명하라"

LLM 은 OpenAI 호환 주소(LLM_BASE_URL, 기본 http://localhost:4000/v1 — 13장의 게이트웨이)로 부른다.
연결이 안 되면 규칙만으로 돌아간다. 실제 값: 번역 10초, 분해 30초, 온도 0, seed 42.
"""
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:4000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen")

# ---------------------------------------------------------------- ① 옮긴다

# 늘 같게 옮겨야 하는 낱말은 표에, 나머지만 모델에
TERM_MAP = {
    "설포라판": "sulforaphane", "브로콜리": "broccoli", "새싹": "sprouts",
    "항암": "anticancer", "임상시험": "clinical trial", "효과": "effect",
    "메커니즘": "mechanism", "활성화": "activation", "당뇨": "diabetes",
    "자폐": "autism", "항염": "anti-inflammatory", "항산화": "antioxidant",
    "복용량": "dosage", "부작용": "side effects", "낙산균": "butyric acid bacteria",
    "프로바이오틱스": "probiotics", "장건강": "gut health",
}
_ASCII = re.compile(r"^[a-zA-Z0-9\s\-\.,]+$")


def _llm(messages, max_tokens=150, temperature=0.0, timeout=30, seed=None):
    """OpenAI 호환 chat/completions. 실패하면 None — 호출한 쪽이 규칙으로 물러선다."""
    try:
        import requests
        body = {"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if seed is not None:
            body["seed"] = seed
        r = requests.post(f"{LLM_BASE_URL}/chat/completions", json=body, timeout=timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def translate_to_english(query: str, use_llm: bool = True) -> str:
    if _ASCII.match(query):
        return query                                   # 이미 영어
    pre = query
    for ko, en in TERM_MAP.items():                    # 표부터 — 늘 같게
        pre = pre.replace(ko, en)
    if _ASCII.match(pre) or not use_llm:
        return pre                                     # 다 옮겨졌거나, 모델을 안 쓰면 여기까지
    hint = ", ".join(f"{k}={v}" for k, v in TERM_MAP.items())
    out = _llm([{"role": "user", "content":
                 f"/no_think Translate this Korean biomedical query to English. "
                 f"Use these exact mappings: {hint}. Output ONLY the translation: {query}"}],
               max_tokens=80, temperature=0.1, timeout=10)
    return out.strip("\"'") if out else pre


# ---------------------------------------------------------------- ② 넓힌다

# 정식 화학명 / 공식 약어만. "broccoli sprout", "green tea" 같은 원료명은 검색을 희석시켜 뺐다.
COMPOUND_SYNONYMS = {
    "sulforaphane": ["SFN", "isothiocyanate sulforaphane", "glucoraphanin sulforaphane"],
    "설포라판": ["sulforaphane", "isothiocyanate sulforaphane"],
    "egcg": ["epigallocatechin gallate", "epigallocatechin-3-gallate"],
    "curcumin": ["diferuloylmethane", "turmeric curcumin"],
    "genistein": ["4',5,7-trihydroxyisoflavone", "soy isoflavone genistein"],
    "resveratrol": ["trans-resveratrol", "3,5,4'-trihydroxystilbene"],
    "butyrate": ["butyric acid", "sodium butyrate", "SCFA", "short-chain fatty acid", "Clostridium butyricum"],
    "butyric acid": ["butyrate", "sodium butyrate", "SCFA", "Clostridium butyricum"],
    "nrf2": ["NFE2L2"],
    "hdac": ["histone deacetylase"],
}


def expand_with_synonyms(query: str, max_expansions: int = 2):
    """질문에 사전의 이름이 보이면, 별칭으로 바꾼 질문을 몇 개 더 만든다."""
    q = query.lower()
    extra = []
    for name, syns in COMPOUND_SYNONYMS.items():
        if name in q:
            for s in syns[:max_expansions]:
                extra.append(re.sub(re.escape(name), s, query, flags=re.IGNORECASE))
    return [query] + extra


# ---------------------------------------------------------------- ③ 쪼갠다

def is_complex_query(question: str) -> bool:
    """다섯 신호 중 둘 이상이면 복합 질문 (실제 규칙 그대로)."""
    indicators = [
        len(question) > 50,
        question.count(",") >= 2,
        any(w in question for w in ["그리고", "및", "또한", "관련", "and", "+"]),
        any(w in question for w in ["기전", "메커니즘", "mechanism", "경로", "pathway"]),
        question.count("?") >= 2,
    ]
    return sum(indicators) >= 2


# LLM 이 서브쿼리에 자꾸 끼워 넣는, 어디에나 있는 말 — 걷어 낸다
META_TERMS = {"mechanism", "mechanisms", "pathway", "pathways", "indirect", "direct", "effect", "effects", "role"}


def filter_meta_terms(queries):
    out = []
    for q in queries:
        words = [w for w in q.split() if w.lower().strip(",.") not in META_TERMS]
        if len(words) >= 2:
            out.append(" ".join(words))
    return out or queries


DECOMPOSE_PROMPT = """당신은 생명과학 연구 논문 검색 전문가입니다.
사용자의 복합 질문을 분석하여, 각 주제별로 최적의 영문 검색 쿼리를 생성하세요.
규칙: 각 서브쿼리는 영어, 2~6개, 5~12단어, 핵심 물질의 동의어 포함
(sulforaphane = SFN, butyric acid = butyrate, Clostridium butyricum = C. butyricum, HDAC = histone deacetylase, Nrf2 = NFE2L2).
반드시 JSON 배열로만 응답. 다른 텍스트 없이."""


def _rule_decompose(question: str):
    """LLM 이 없을 때의 물러섬 — 이음말·쉼표로 쪼개고 영어로 옮긴다."""
    parts = re.split(r"\s*(?:,|그리고|및|또한|\band\b|\+)\s*", question)
    parts = [p.strip(" .?") for p in parts if len(p.strip(" .?")) >= 4]
    return [translate_to_english(p, use_llm=False) for p in parts] or [translate_to_english(question, use_llm=False)]


def decompose_query(question: str, use_llm: bool = True):
    """복합 질문 → 영어 서브쿼리 2~6개. 온도 0, seed 42 — 같은 질문이면 늘 같은 쪼개기."""
    subs = None
    if use_llm:
        out = _llm([{"role": "system", "content": DECOMPOSE_PROMPT},
                    {"role": "user", "content": f"{question} /no_think"}],
                   max_tokens=512, temperature=0.0, timeout=30, seed=42)
        if out:
            if out.startswith("```"):
                out = out.split("\n", 1)[1].rsplit("```", 1)[0]
            m = re.search(r"\[.*\]", out, re.DOTALL)
            try:
                subs = [q for q in json.loads(m.group(0) if m else out) if isinstance(q, str)][:6]
            except Exception:
                subs = None
    if not subs:
        subs = _rule_decompose(question)
    return filter_meta_terms(subs)


def prepare_queries(question: str, use_llm: bool = True):
    """세 겹을 한 번에: 복합이면 쪼개고, 아니면 그대로. 각 쿼리는 (한국어, 영어) 두 벌."""
    subs = decompose_query(question, use_llm) if is_complex_query(question) else [question]
    return [(sq, translate_to_english(sq, use_llm)) for sq in subs]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "설포라판의 Nrf2 경로와 HDAC 억제, 그리고 면역 조절 기전을 설명하라"
    print("질문      :", q)
    print("복합 질문?:", is_complex_query(q))
    print("영어로    :", translate_to_english(q, use_llm=False))
    print("동의어    :", expand_with_synonyms(translate_to_english(q, use_llm=False)))
    print("서브쿼리  :", decompose_query(q, use_llm=False))
