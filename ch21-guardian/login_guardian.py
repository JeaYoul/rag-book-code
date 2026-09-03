#!/usr/bin/env python3
"""
login_guardian.py — 누가 들어왔는가 (21장)

    python login_guardian.py             이 기계 + 원격 기계의 접속자
    python login_guardian.py --demo      조회 실패가 왜 무서운지 보여 준다

내가 접속하면 내 휴대폰이 울린다. 그것이 정상이다.
내가 접속하지 않았는데 울리면, 그때가 문제다.

이 파일에서 가장 중요한 줄은 알림을 보내는 줄이 아니라,
조회에 실패했을 때 이전 상태를 그대로 두는 줄이다.
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import load_state, save_state, send   # noqa: E402

HOSTS = [("이 기계", None), ("다른 기계", "user@192.168.10.50")]   # ssh 접속 문자열


def sessions(host, ssh):
    """who 를 읽어 {키: 정보}. 조회 자체에 실패하면 None — 빈 사전과 구분한다."""
    try:
        cmd = (["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh, "who"]
               if ssh else ["who"])
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=25).stdout
    except Exception:
        return None
    res = {}
    for ln in out.strip().splitlines():
        p = ln.split()
        if len(p) < 2:
            continue
        src = p[-1].strip("()") if p[-1].startswith("(") else "로컬콘솔"
        res[f"{host}|{p[0]}|{p[1]}"] = {"host": host, "user": p[0], "tty": p[1],
                                        "src": src, "time": " ".join(p[2:4]) if len(p) >= 4 else ""}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        _demo()
        return 0

    prev = load_state("login")
    now, failed = {}, []
    for host, ssh in HOSTS:
        r = sessions(host, ssh)
        if r is None:
            failed.append(host)
            # ★ 조회에 실패한 것과 아무도 없는 것은 다르다.
            #   이 줄이 없으면 네트워크가 잠깐 끊길 때마다 거짓 알림이 두 통씩 간다.
            now.update({k: v for k, v in prev.items() if v.get("host") == host})
        else:
            now.update(r)

    new = [v for k, v in now.items() if k not in prev]
    gone = [v for k, v in prev.items() if k not in now]

    if new:
        send("🔑 서버 로그인\n\n" + "\n\n".join(
            f"{v['host']}  {v['user']}\n출처: {v['src']}\n시각: {v['time']}  ({v['tty']})" for v in new))
    if gone:
        send("🚪 접속 종료\n\n" + "\n".join(
            f"{v['host']}  {v['user']}  ({v['src']})" for v in gone))

    save_state("login", now)
    print(f"세션 {len(now)}개 | 신규 {len(new)} | 종료 {len(gone)}"
          + (f" | 조회실패 {','.join(failed)}" if failed else ""))
    return 0


def _demo():
    prev = {"다른 기계|npk|pts/0": {"host": "다른 기계", "user": "npk", "tty": "pts/0", "src": "192.168.10.9", "time": "09:12"}}

    print("=== 잘못 만들면 ================================================")
    print("  네트워크가 잠깐 끊겨 조회 실패 → 결과를 빈 사전으로 처리하면:")
    now_bad = {}
    print(f"    '접속 종료' 알림 {len([k for k in prev if k not in now_bad])}통  ← 거짓말")
    print("  네트워크 복구 → 같은 세션이 다시 보이면:")
    print(f"    '서버 로그인' 알림 {len([k for k in prev if k not in now_bad])}통  ← 또 거짓말")
    print("  아무 일도 없었는데 두 통이 갔다. 이런 알림은 이틀이면 무시당한다.")

    print("\n=== 제대로 만들면 ==============================================")
    now_ok = dict(prev)          # 조회 실패 → 이전 상태를 그대로 둔다
    print(f"    신규 {len([k for k in now_ok if k not in prev])} · 종료 {len([k for k in prev if k not in now_ok])}  → 알림 없음")
    print("  조회에 실패한 것과 아무도 없는 것은 다르다. 그 한 줄이 이 차이를 만든다.")


if __name__ == "__main__":
    sys.exit(main())
