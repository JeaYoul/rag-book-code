#!/usr/bin/env python3
"""
rag_bot.py — 주머니 속의 연구실 (21장)

    python rag_bot.py                       텔레그램 봇으로 (토큰 필요)
    python rag_bot.py --ask "질문"          한 번만 물어보고 끝 (텔레그램 없이)
    python rag_bot.py --ask "질문" --fake    LLM·검색 서버 없이 흐름만

밭에서, 차에서, 잠들기 전에 휴대폰으로 묻는다.
19장에서 만든 도구 창구(mcpo)의 논문 검색 주소를 그대로 부른다.

이 봇의 핵심은 to_en() 한 함수다.
한국어로 물으면 영어 논문이 안 잡힌다. 묻는 말과 찾는 말은 같은 언어여야 한다.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HOME = Path(os.getenv("GUARDIAN_HOME", str(Path.home())))
RAG = os.getenv("RAG_SEARCH_URL", "http://localhost:8000/rag/search_papers")
LLM = os.getenv("LLM_URL", "http://localhost:4000/v1/chat/completions")
MODEL = os.getenv("LLM_MODEL", "qwen")
FAKE = os.getenv("BOT_FAKE") == "1"

ANSWER_RULES = """아래 논문 발췌를 근거로 질문에 한국어로 답하라.
- 근거 문서를 [문서N] 형식으로 인용하라
- 발췌에 없는 내용은 추측하지 말고 모른다고 하라
- 각 항목 사이에 빈 줄을 하나 넣어 문단을 구분하라
- 간결하게 핵심만"""


# ---------------------------------------------------------------- 모델

def ask_llm(prompt, max_tokens=4000):
    if FAKE:
        if "영어 논문 검색용 키워드" in prompt:
            return "sulforaphane HDAC inhibition mechanism"
        return ("설포라판은 HDAC 활성을 억제한다는 근거가 있다 [문서1].\n\n"
                "병용 시너지에 대한 직접 근거는 발췌 범위에서 찾지 못했다.")
    import requests
    r = requests.post(LLM, json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                                 "max_tokens": max_tokens, "temperature": 0.3,
                                 "chat_template_kwargs": {"enable_thinking": False}}, timeout=600)
    r.raise_for_status()
    m = r.json()["choices"][0]["message"]
    # Qwen 추론 모델은 content 가 비고 reasoning_content 에 들어오는 때가 있다 (12·16장)
    return (m.get("content") or m.get("reasoning_content") or "(응답 없음)").strip()


def to_en(q):
    """한국어 질문 → 영어 검색 키워드. 이 함수 하나가 봇의 쓸모를 갈랐다."""
    try:
        r = ask_llm("다음 질문을 영어 논문 검색용 키워드로 바꿔라. "
                    "설명 없이 키워드만 한 줄로 출력하라.\n\n" + q)
        return r.split("\n")[0].strip().strip("*\"'").strip()[:200] or q
    except Exception:
        return q          # 번역이 안 됐다고 답을 못 주면 안 된다


def search(query, top_k=20):
    if FAKE:
        return [{"paper_id": "PMC000001", "title": "Sulforaphane and butyrate inhibit HDAC in colon cells",
                 "abstract": "Sulforaphane derived from broccoli sprouts inhibits HDAC activity.",
                 "matched_content": "SFN reduced HDAC activity by activating Nrf2."}]
    import requests
    r = requests.post(RAG, json={"query": query, "top_k": top_k}, timeout=120)
    r.raise_for_status()
    return r.json().get("results", [])


def answer(q):
    eq = to_en(q)
    print("  검색어:", eq)
    docs = search(eq)
    if not docs:
        return "관련 논문을 찾지 못했습니다."
    ctx = "\n\n".join(
        f"[문서{i+1}] {d.get('title','')}\nPMC: {d.get('paper_id','')}\n"
        f"초록: {(d.get('abstract') or '')[:2000]}\n"
        f"관련구절: {(d.get('matched_content') or '')[:800]}"
        for i, d in enumerate(docs))
    out = ask_llm(f"{ANSWER_RULES}\n\n질문: {q}\n\n--- 논문 발췌 ---\n{ctx}")
    refs = "\n".join(f"[문서{i+1}] {d.get('paper_id','')} — {d.get('title','')[:60]}"
                     for i, d in enumerate(docs))
    return f"{out}\n\n───\n📚 참고 논문\n{refs}"


# ---------------------------------------------------------------- 텔레그램

def fmt(t):
    """휴대폰 화면에서 읽히게. 마크다운 기호를 걷어내고 문단을 띄운다."""
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", t)
    t = re.sub(r"(?m)^#{1,6}\s*", "", t)
    t = t.replace("`", "").replace("*", "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def run_bot():
    import requests
    env = {}
    f = HOME / ".rag_bot_env"
    if f.exists():
        env = dict(l.strip().split("=", 1) for l in f.read_text(encoding="utf-8").splitlines() if "=" in l)
    token, owner = env.get("TELEGRAM_TOKEN", "").strip(), env.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not owner:
        print("~/.rag_bot_env 에 TELEGRAM_TOKEN 과 TELEGRAM_CHAT_ID 가 필요하다.")
        print("토큰 없이 흐름만 보려면:  python rag_bot.py --ask \"질문\" --fake")
        return 1
    api = f"https://api.telegram.org/bot{token}"

    def send(chat, text):
        body = fmt(text)
        for i in range(0, len(body), 3900):        # 텔레그램 한 통 한도
            requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": body[i:i+3900]}, timeout=30)

    offset = None
    print("논문 봇 시작 (Ctrl+C 종료)")
    while True:
        try:
            r = requests.get(f"{api}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                chat = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()
                # ★ 내 대화창이 아니면 무시한다. 봇 주소는 누구나 알아낼 수 있다
                if chat != owner or not text:
                    continue
                if text.startswith("/"):
                    send(chat, "논문에 대해 질문하세요.\n예) 설포라판의 HDAC 억제 기전은?")
                    continue
                print("질문:", text[:40])
                send(chat, "🔍 논문 검색 중입니다...")
                try:
                    send(chat, answer(text))
                except Exception as e:
                    send(chat, f"처리 중 오류: {e}")
        except Exception as e:
            print("루프 오류:", e, file=sys.stderr)
            time.sleep(5)      # 무슨 일이 있어도 루프는 계속 돈다


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ask", help="텔레그램 없이 한 번만 물어본다")
    ap.add_argument("--fake", action="store_true", help="LLM·검색 서버 없이 흐름만")
    a = ap.parse_args()
    if a.fake:
        globals()["FAKE"] = True
    if a.ask:
        print(answer(a.ask))
        return 0
    return run_bot()


if __name__ == "__main__":
    sys.exit(main())
