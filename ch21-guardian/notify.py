#!/usr/bin/env python3
"""
notify.py — 파수꾼들이 공통으로 쓰는 두 가지 (21장)

    send(text)                  텔레그램으로 보낸다. 토큰이 없으면 화면에 찍는다
    load_state / save_state     지난번에 본 것을 파일에 적어 두고 다시 읽는다

이 장의 핵심은 말하는 기술이 아니라 침묵하는 기술이다.
침묵하려면 "지난번"을 기억해야 하고, 그 기억이 여기 있다.

토큰은 코드에 넣지 않는다. 홈 폴더의 ~/.guardian_env 에서 읽는다:
    TELEGRAM_TOKEN=...
    TELEGRAM_CHAT_ID=...
없으면 자동으로 연습 모드(화면 출력)로 돈다. GUARDIAN_DRY=1 이면 토큰이 있어도 화면으로만.
"""
import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HOME = Path(os.getenv("GUARDIAN_HOME", str(Path.home())))
ENV_FILE = HOME / ".guardian_env"
DRY = os.getenv("GUARDIAN_DRY") == "1"


def _env():
    """~/.guardian_env 를 읽는다. 없으면 빈 사전."""
    if not ENV_FILE.exists():
        return {}
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def force_dry(reason=""):
    """시연·연습에서는 절대 밖으로 나가지 않게 잠근다.

    이것이 없어서 사고가 났다. 시연 모드로 돌렸는데 서버에는 토큰 파일이 있었고,
    가짜 상태 전이가 진짜 알림이 되어 휴대폰으로 갔다.
    보내는 코드를 시험할 때는, 보내지 않는 것이 기본값이어야 한다.
    """
    global DRY
    DRY = True
    if reason:
        print(f"[연습 모드 고정] {reason}")


def send(text: str) -> bool:
    """텔레그램으로 한 통. 토큰이 없거나 DRY 면 화면에 찍고 끝낸다."""
    env = _env()
    token, chat = env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if DRY or not token or not chat:
        print("─" * 46)
        print(text)
        print("─" * 46 + "  (연습 모드 — 실제로 보내지 않음)")
        return True
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=30)
    ok = r.json().get("ok", False)
    if not ok:
        print("발송 실패:", r.text, file=sys.stderr)
    return ok


def load_state(name: str) -> dict:
    """지난번에 본 것. 처음이면 빈 사전 — 그래서 첫 실행은 조용하다."""
    f = HOME / f".{name}_state.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}          # 깨진 상태 파일 때문에 파수꾼이 죽지 않게


def save_state(name: str, state: dict) -> None:
    (HOME / f".{name}_state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8")


def diff_bool(prev: dict, now: dict):
    """상태 전이만 골라낸다.  (죽은 것, 살아난 것)

    처음 보는 이름은 어느 쪽에도 넣지 않는다 — 비교할 어제가 없을 때는 말하지 않는다.
    """
    down = [k for k, v in now.items() if prev.get(k) is True and not v]
    back = [k for k, v in now.items() if prev.get(k) is False and v]
    return down, back
