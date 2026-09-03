#!/usr/bin/env bash
# weekly_check.sh — 일주일에 한 번 이것만 보면 된다 (20장)
#
#   ./weekly_check.sh                                  기본 서비스 목록으로
#   ./weekly_check.sh svc1 svc2 ...                    직접 지정
#   UNITS="a b" ./weekly_check.sh
#
# 핵심은 재시작 횟수다. 그것이 서비스의 체온이다.
# 0 이면 건강하고, 조용히 늘어나고 있으면 어딘가 아프다.
# 반드시 전부 늘어놓고 봐라 — 사고의 원인은 다른 서비스에 있을 수 있다.
set -uo pipefail

DEFAULT="litellm-qwen qwen3-reranker mcpo rag-bot bionemo-app streamlit-rag entrez-mcp"
UNITS="${*:-${UNITS:-$DEFAULT}}"

echo "=== 실패한 것이 있는가 ==========================================="
failed=$(systemctl list-units --failed --no-pager --no-legend 2>/dev/null || true)
if [ -n "$failed" ]; then echo "$failed"; else echo "없음"; fi

echo; echo "=== 재시작 횟수 — 서비스의 체온 ==================================="
printf "%-22s %-10s %-12s %-6s %s\n" "서비스" "상태" "정책" "재시작" "마지막 기동"
for u in $UNITS; do
  # --value 로 한 항목씩 읽는다. eval 로 한꺼번에 읽으면 공백 든 값(기동 시각)에서 깨진다
  state=$(systemctl show "$u" --no-pager -p ActiveState --value 2>/dev/null || true)
  [ -z "$state" ] && continue
  policy=$(systemctl show "$u" --no-pager -p Restart --value 2>/dev/null)
  nres=$(systemctl show "$u" --no-pager -p NRestarts --value 2>/dev/null)
  since=$(systemctl show "$u" --no-pager -p ExecMainStartTimestamp --value 2>/dev/null)
  mark=""
  case "${nres:-0}" in ""|0) ;; *) mark=" <--" ;; esac
  printf "%-22s %-10s %-12s %-6s %s%s\n" "$u" "$state" "${policy:-?}" "${nres:-0}" "${since:-(없음)}" "$mark"
done
echo "<-- 표시가 있으면, 그 서비스가 죽은 시각과 다른 서비스를 멈춘 시각을 나란히 놓고 봐라."
echo "   journalctl -u A -u B --no-pager | grep -E 'Started|Stopped|Scheduled restart' | tail -30"

echo; echo "=== 지난 7일의 오류 =============================================="
any_err=0
for u in $UNITS; do
  # "-- No entries --" 같은 안내문은 오류가 아니다. 그것까지 세면 전부 1줄로 나온다
  errs=$(journalctl -u "$u" --since "7 days ago" -p err --no-pager 2>/dev/null | grep -v '^-- ' || true)
  n=$(printf '%s' "$errs" | grep -c . || true)
  if [ "${n:-0}" -gt 0 ]; then
    any_err=1
    echo "--- $u ($n 줄) ---"
    printf '%s\n' "$errs" | tail -5
  fi
done
[ "$any_err" = "0" ] && echo "지난 7일 오류 없음"

echo; echo "=== 로그가 얼마나 남아 있는가 ====================================="
journalctl --disk-usage 2>/dev/null
echo "가장 오래된 기록: $(journalctl --no-pager -o short-iso 2>/dev/null | head -1 | cut -d' ' -f1)"
echo "→ 이 날짜보다 이전의 장애는 로그로 되짚을 수 없다. 코드 저장소의 커밋 메시지가 마지막 기록이다."

echo; echo "=== 디스크 ======================================================="
df -h / 2>/dev/null | tail -1

echo; echo "=== 안 쓰는데 켜져 있는 것 ========================================"
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo "(docker 없음)"
echo "→ 쓰지 않기로 한 것이 목록에 있으면 꺼라. 안 쓰는 서비스는 지켜야 할 문이다."
