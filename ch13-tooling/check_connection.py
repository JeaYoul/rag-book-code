#!/usr/bin/env python3
"""check_connection.sh 의 파이썬 판. 표준 라이브러리만 쓴다 (윈도우에서도 돈다).

    python check_connection.py

환경 변수 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN 을 읽는다.
없으면 같은 폴더의 .env 에서 LITELLM_MASTER_KEY 를 읽는다.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_dotenv() -> None:
    p = Path(__file__).with_name(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_dotenv()

BASE = os.environ.get("ANTHROPIC_BASE_URL", "http://192.168.10.51:4000")
KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("LITELLM_MASTER_KEY", "")
VLLM = os.environ.get("VLLM_BASE", "http://192.168.10.50:8000")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def bad(msg: str) -> None:
    print(f"  [X ] {msg}")
    sys.exit(1)


def call(url: str, body=None, timeout: int = 120):
    headers = {
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


print("1. 주소 형식")
if not BASE.startswith(("http://", "https://")):
    bad(f"{BASE}  <- http:// 가 빠졌다.")
ok(BASE)

print("2. 열쇠")
if not KEY:
    bad("열쇠가 비었다. ANTHROPIC_AUTH_TOKEN 또는 .env 의 LITELLM_MASTER_KEY.")
ok("ANTHROPIC_AUTH_TOKEN 있음")
if os.environ.get("ANTHROPIC_API_KEY"):
    bad("ANTHROPIC_API_KEY 가 남아 있다. 지워라 (401의 흔한 원인).")
ok("ANTHROPIC_API_KEY 없음 (정상)")

print("3. 살아 있는가")
try:
    call(f"{VLLM}/v1/models", timeout=5)
    ok(f"vLLM {VLLM}")
except Exception as e:  # noqa: BLE001
    print(f"  [! ] vLLM 응답 없음 ({e}). Spark1 부터 보라.")
try:
    call(f"{BASE}/v1/models", timeout=5)
    ok(f"게이트웨이 {BASE}")
except urllib.error.HTTPError as e:
    if e.code == 401:
        bad("게이트웨이는 살아 있는데 열쇠를 거절 (401). master_key 와 AUTH_TOKEN 이 같은가?")
    bad(f"게이트웨이 응답 {e.code}")
except Exception as e:  # noqa: BLE001
    bad(f"연결 자체가 안 됨 ({e}). 게이트웨이가 죽었거나 포트/방화벽 문제.")

print("4. OpenAI 형식으로 한 마디")
r = call(
    f"{BASE}/v1/chat/completions",
    {
        "model": "qwen",
        "messages": [{"role": "user", "content": "한 단어로만 답하라: 산골"}],
        "max_tokens": 20,
    },
)
ok(r["choices"][0]["message"]["content"][:80])

print("5. Anthropic 형식으로 한 마디 (클로드 코드가 쓰는 길)")
r = call(
    f"{BASE}/v1/messages",
    {
        "model": "qwen",
        "max_tokens": 20,
        "messages": [{"role": "user", "content": "한 단어로만 답하라: 불사조"}],
    },
)
text = next((b.get("text", "") for b in r.get("content", []) if b.get("type") == "text"), "")
ok(text[:80])

print()
print("다섯 자리 모두 통과. 이제 claude 를 띄우고 /status 를 보라.")
