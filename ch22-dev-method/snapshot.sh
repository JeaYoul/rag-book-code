#!/usr/bin/env bash
# snapshot.sh — 지침서에서 낡는 부분만 자동으로 갈아 끼운다 (22장)
#
#   ./snapshot.sh --dry-run              무엇을 쓸지 화면에만
#   ./snapshot.sh CLAUDE.md              그 파일의 SNAPSHOT 구간을 갈아 끼운다
#   PG_DSN=... ./snapshot.sh CLAUDE.md   데이터베이스 현황까지
#
# 왜 이것이 필요한가.
#   22장에서 확인한 것: 지침서의 "현재 데이터 현황" 절에 3월 날짜가 박혀 있었고,
#   그 뒤로 데이터가 계속 늘었는데 파일은 7월까지 손대지 않았다.
#   AI 는 지금도 그 파일을 읽고 3월의 숫자를 믿는다.
#
#   지침서는 만드는 순간부터 낡는다. 그래서 낡는 부분을 사람 손에서 떼어 냈다.
#   사람이 쓴 부분(표 이름·경로·원칙·건드리면 안 되는 것)은 건드리지 않는다.
#   아래 두 표시 사이만 갈아 끼운다:
#       <!-- SNAPSHOT:BEGIN -->  …  <!-- SNAPSHOT:END -->
set -uo pipefail

BEGIN_MARK="<!-- SNAPSHOT:BEGIN"
END_MARK="<!-- SNAPSHOT:END -->"
DRY=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    *) TARGET="$arg" ;;
  esac
done
[ -z "$TARGET" ] && DRY=1

# 이 목록을 자기 프로젝트에 맞게 고쳐라
SERVICES="${SNAPSHOT_SERVICES:-postgresql mongod docker}"
TABLES="${SNAPSHOT_TABLES:-}"          # 예: "papers chunks users"

# ---------------------------------------------------------------- 모으기
gather() {
  echo "## 7. 현재 현황"
  echo
  echo "_이 절은 \`snapshot.sh\` 가 자동으로 씁니다. 손으로 고치지 마십시오._"
  echo "_확인 시각: $(date '+%Y-%m-%d %H:%M') · 기계: $(hostname)_"
  echo

  # --- 데이터 건수 -------------------------------------------------------
  if [ -n "${PG_DSN:-}" ] && command -v psql >/dev/null 2>&1; then
    echo "### 데이터"
    echo
    echo "| 표 | 줄 수 |"
    echo "|---|---|"
    if [ -n "$TABLES" ]; then
      for t in $TABLES; do
        n=$(psql "$PG_DSN" -tAc "SELECT count(*) FROM $t;" 2>/dev/null || echo "?")
        echo "| \`$t\` | $n |"
      done
    else
      # 표 목록을 모르면 통계에서 큰 것 열 개
      psql "$PG_DSN" -tAc "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;" 2>/dev/null \
        | awk -F'|' '{printf "| `%s` | %s |\n", $1, $2}'
    fi
    echo
  else
    echo "### 데이터"
    echo
    echo "_PG_DSN 이 없어 세지 못했습니다. 정확한 값은 직접 세어 보십시오._"
    echo
  fi

  # --- 서비스 ------------------------------------------------------------
  if command -v systemctl >/dev/null 2>&1; then
    echo "### 서비스"
    echo
    echo "| 서비스 | 상태 | 재시작 |"
    echo "|---|---|---|"
    for s in $SERVICES; do
      st=$(systemctl show "$s" --no-pager -p ActiveState --value 2>/dev/null || true)
      [ -z "$st" ] && continue
      nr=$(systemctl show "$s" --no-pager -p NRestarts --value 2>/dev/null)
      echo "| \`$s\` | $st | ${nr:-0} |"
    done
    echo
  fi

  # --- 코드 ------------------------------------------------------------
  if git rev-parse --git-dir >/dev/null 2>&1; then
    echo "### 코드"
    echo
    echo "- 커밋 $(git rev-list --count HEAD)개 · $(git log --reverse --pretty=%ad --date=short | head -1) ~ $(git log -1 --pretty=%ad --date=short)"
    echo "- 마지막 커밋: \`$(git log -1 --pretty=%s | cut -c1-70)\`"
    br=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    dirty=$(git status --porcelain | wc -l)
    echo "- 가지 \`$br\` · 커밋하지 않은 변경 ${dirty}건"
    echo
  fi

  echo "> 숫자는 위 시각에 센 것입니다. 오래되었으면 \`./snapshot.sh CLAUDE.md\` 를 다시 돌리십시오."
}

# ---------------------------------------------------------------- 쓰기
BODY="$(gather)"

if [ "$DRY" = "1" ]; then
  echo "===== 이 내용을 SNAPSHOT 구간에 씁니다 (--dry-run) ====="
  echo "$BODY"
  exit 0
fi

[ -f "$TARGET" ] || { echo "그런 파일이 없다: $TARGET"; exit 1; }
grep -q "$BEGIN_MARK" "$TARGET" || {
  echo "표시가 없다. $TARGET 맨 아래에 두 줄을 넣어라:"
  echo "  <!-- SNAPSHOT:BEGIN --> 와 <!-- SNAPSHOT:END -->"
  exit 1
}

TMP=$(mktemp)
awk -v body="$BODY" -v b="$BEGIN_MARK" -v e="$END_MARK" '
  index($0, b) { print; print ""; print body; print ""; skip=1; next }
  index($0, e) { skip=0 }
  !skip { print }
' "$TARGET" > "$TMP"

# 안전장치: 결과가 원본보다 크게 줄었으면 쓰지 않는다 (사람이 쓴 부분을 지웠을 수 있다)
before=$(wc -l < "$TARGET"); after=$(wc -l < "$TMP")
if [ "$after" -lt $(( before / 2 )) ]; then
  echo "결과가 원본의 절반 미만이다 ($before → $after). 쓰지 않고 멈춘다."
  echo "확인용 파일: $TMP"
  exit 2
fi

cp "$TARGET" "$TARGET.bak"
mv "$TMP" "$TARGET"
echo "갱신함: $TARGET  ($before → $after 줄, 백업 $TARGET.bak)"
echo "사람이 쓴 부분은 건드리지 않았다. git diff 로 확인하라."
