#!/usr/bin/env bash
# zombie_check.sh — 좀비를 찾아내고 죽이는 다섯 단계 (20장)
#
#   ./zombie_check.sh                     보기만 한다 (아무것도 죽이지 않는다)
#   ./zombie_check.sh --port 8501         그 포트를 쥔 것이 누구인지까지
#   ./zombie_check.sh --port 8501 --kill  고아면 죽인다 (TERM → 3초 → KILL)
#
# 말을 먼저 나눈다.
#   진짜 좀비(Z) = 이미 죽었는데 이름표만 남은 것. 죽일 수 없다. 부모를 다시 띄워야 한다.
#   고아         = 살아서 포트를 쥔 것. 다음 기동을 막는 진짜 범인.
set -uo pipefail

PORT=""; DO_KILL=0; UNIT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --unit) UNIT="$2"; shift 2 ;;
    --kill) DO_KILL=1; shift ;;
    *) echo "쓰는 법: $0 [--port 8501] [--unit streamlit-rag] [--kill]"; exit 1 ;;
  esac
done

echo "=== 1. 진짜 좀비(Z) ==============================================="
ZOMBIES=$(ps -eo pid,ppid,stat,comm | awk 'NR==1 || $3 ~ /Z/')
echo "$ZOMBIES"
N=$(echo "$ZOMBIES" | tail -n +2 | grep -c . || true)
if [ "$N" -gt 0 ]; then
  echo "→ $N 개. 이것은 kill 로 죽지 않는다. 위 두 번째 칸(PPID)의 부모를 다시 띄워라."
  echo "   부모가 누구인지:  ps -p \$(ps -eo ppid,stat | awk '\$2 ~ /Z/ {print \$1}' | sort -u | tr '\\n' ',' | sed 's/,\$//') -o pid,cmd"
  [ "$N" -gt 100 ] && echo "   ⚠ 100개가 넘는다 — 부모 프로그램이 자식을 거두지 않고 있다. 코드를 봐야 한다."
else
  echo "→ 없음 (정상)"
fi

if [ -z "$PORT" ]; then
  echo; echo "포트를 주면 2단계부터 봅니다:  $0 --port 8501"
  exit 0
fi

echo; echo "=== 2. $PORT 포트를 쥔 것 ========================================"
SS=$(ss -tlnp 2>/dev/null | grep ":$PORT " || true)
if [ -z "$SS" ]; then
  echo "→ 아무도 쥐고 있지 않다."
  exit 0
fi
echo "$SS"
PID=$(echo "$SS" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
if [ -z "$PID" ]; then
  echo "→ 번호가 안 보인다. 남의 계정 프로세스다. sudo 로 다시 실행하라."
  exit 0
fi
echo "→ PID $PID"
ps -p "$PID" -o pid,ppid,stat,etime,rss,cmd --no-headers

echo; echo "=== 3. 이것이 서비스 소속인가 ====================================="
CG=$(cat "/proc/$PID/cgroup" 2>/dev/null | head -1)
echo "제어 그룹: ${CG:-(읽을 수 없음)}"
OWNER=""
case "$CG" in
  *".service"*) OWNER=$(echo "$CG" | grep -o '[a-zA-Z0-9_.@-]*\.service' | tail -1) ;;
esac
PPID_=$(ps -p "$PID" -o ppid= | tr -d ' ')
if [ -n "$OWNER" ]; then
  echo "→ 소속 있음: $OWNER   (systemd 가 아는 프로세스다)"
else
  if [ "$PPID_" = "1" ]; then
    echo "→ 소속 없음, 부모 PID=1 → 고아다. 이것이 포트를 막고 있다."
  else
    echo "→ 소속 없음, 부모 PID=$PPID_ (터미널에서 띄운 것일 수 있다)"
  fi
fi

echo; echo "=== 4. 죽이는 법 ================================================="
if [ -n "$OWNER" ]; then
  echo "systemd 에게 시킨다. 제어 그룹 전체가 한 번에 정리된다:"
  echo "   sudo systemctl kill -s TERM ${UNIT:-$OWNER}"
  echo "   sudo systemctl stop        ${UNIT:-$OWNER}     # 아예 멈출 때"
  [ "$DO_KILL" = "1" ] && echo "   (--kill 은 서비스 소속에는 쓰지 않는다. 위 명령을 쓰라.)"
else
  echo "고아다. 번호로 직접 죽인다. 부드럽게 먼저, 3초 뒤에도 살아 있으면 강하게:"
  echo "   kill -TERM $PID; sleep 3; kill -KILL $PID"
  if [ "$DO_KILL" = "1" ]; then
    echo "→ --kill 이 붙었으므로 실행한다."
    kill -TERM "$PID" 2>/dev/null && sleep 3
    if kill -0 "$PID" 2>/dev/null; then
      echo "   TERM 으로 안 죽는다. KILL 을 보낸다."
      kill -KILL "$PID" 2>/dev/null
    fi
    sleep 1
    kill -0 "$PID" 2>/dev/null && echo "   ✗ 아직 살아 있다 (권한 문제일 수 있다)" || echo "   ✓ 정리됨"
  fi
fi
echo
echo "pkill -f 이름 은 쓰지 마라. 같은 글자를 쓰는 남의 프로세스까지 죽는다."

echo; echo "=== 5. 다시 생기지 않게 =========================================="
echo "고아는 스크립트가 자식을 낳고 물러날 때 생긴다 (Type=forking)."
echo "Type=simple 로 프로그램을 직접 띄우면 systemd 가 자기 자식을 끝까지 붙든다."
echo "그러면 위 네 단계를 할 일이 아예 없어진다.  → systemd/rag-home.service 를 보라."
