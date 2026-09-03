#!/usr/bin/env python3
"""
health_guardian.py — 여러 곳을 지켜보다가, 달라졌을 때만 부른다 (21장)

    python health_guardian.py            5분마다 크론으로 도는 그 모습
    python health_guardian.py --demo     일부러 하나를 죽여 상태 전이를 보여 준다

살아 있음을 확인하는 방법은 대상마다 다르다. 그래서 네 가지를 쓴다.
    http  주소를 불러 본다      — 가장 확실하다. 응답이 오면 정말 일하고 있다
    port  포트에 접속해 본다    — 웹 주소가 없는 데이터베이스 같은 것
    svc   서비스 상태를 묻는다  — systemd 가 아는 것 (20장)
    proc  프로세스가 있는지 본다 — 그것도 없는 것
"""
import argparse
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import diff_bool, load_state, save_state, send   # noqa: E402

# (표시명, 방식, 대상)  — 실제 시스템에서는 열 개다. 여기서는 뼈대만
CHECKS = [
    ("LLM 서버",     "http", "http://192.168.10.50:8000/v1/models"),
    ("도구 창구",     "http", "http://localhost:8000/rag/openapi.json"),
    ("논문 검색 앱",  "http", "http://localhost:8501"),
    ("리랭커",       "port", 8090),
    ("문서 DB",      "port", 27017),
    ("관계형 DB",    "svc",  "postgresql"),
    ("게이트웨이",    "svc",  "litellm-qwen"),
    ("논문 봇",      "svc",  "rag-bot"),
]


def alive(kind, target, timeout=10) -> bool:
    try:
        if kind == "http":
            import requests
            return requests.get(target, timeout=timeout).status_code < 500
        if kind == "port":
            with socket.create_connection(("127.0.0.1", int(target)), timeout=5):
                return True
        if kind == "svc":
            return subprocess.run(["systemctl", "is-active", "--quiet", target]).returncode == 0
        if kind == "proc":
            return subprocess.run(["pgrep", "-f", target], capture_output=True).returncode == 0
    except Exception:
        return False          # 못 닿으면 죽은 것으로 본다
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="가짜 상태로 전이를 보여 준다 (아무것도 두드리지 않음)")
    a = ap.parse_args()

    if a.demo:
        _demo()
        return 0

    prev = load_state("health")
    now = {name: alive(kind, target) for name, kind, target in CHECKS}
    down, back = diff_bool(prev, now)

    if down:
        send("🔴 서비스 중단\n\n" + "\n".join(f"· {n}" for n in down))
    if back:
        send("🟢 서비스 복구\n\n" + "\n".join(f"· {n}" for n in back))

    save_state("health", now)
    bad = [n for n, ok in now.items() if not ok]
    # 이 한 줄이 5분마다 로그에 쌓인다. 20장에서 로그가 25MB까지 자란 이유다.
    # 제대로 하려면 이것도 down/back 이 있을 때만 남겨야 한다.
    print("점검 완료 |", "전체 정상" if not bad else "중단: " + ", ".join(bad))
    return 0


def _demo():
    """토큰도 서버도 없이, 침묵의 규칙만 보여 준다."""
    print("=== 1회차 — 처음이라 비교할 어제가 없다 =========================")
    prev, now = {}, {"리랭커": True, "논문 봇": True, "관계형 DB": True}
    d, b = diff_bool(prev, now)
    print(f"  전이: 중단 {d} · 복구 {b}   → 알림 없음 (처음 켰다고 여러 통 오지 않는다)")

    print("\n=== 2회차 — 아무것도 달라지지 않았다 ============================")
    prev = now
    d, b = diff_bool(prev, now)
    print(f"  전이: 중단 {d} · 복구 {b}   → 알림 없음 (계속 정상이면 말하지 않는다)")

    print("\n=== 3회차 — 리랭커가 죽었다 ====================================")
    now = dict(prev, **{"리랭커": False})
    d, b = diff_bool(prev, now)
    print(f"  전이: 중단 {d} · 복구 {b}")
    if d:
        send("🔴 서비스 중단\n\n" + "\n".join(f"· {n}" for n in d))

    print("\n=== 4회차 — 아직 죽어 있다 =====================================")
    prev = now
    d, b = diff_bool(prev, now)
    print(f"  전이: 중단 {d} · 복구 {b}   → 알림 없음 (이미 알려 줬다)")

    print("\n=== 5회차 — 되살아났다 =========================================")
    now = dict(prev, **{"리랭커": True})
    d, b = diff_bool(prev, now)
    print(f"  전이: 중단 {d} · 복구 {b}")
    if b:
        send("🟢 서비스 복구\n\n" + "\n".join(f"· {n}" for n in b))
    print("\n다섯 번 돌아 알림은 두 통. 이것이 이 장의 전부다.")


if __name__ == "__main__":
    sys.exit(main())
