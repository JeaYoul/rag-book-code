#!/usr/bin/env bash
# restore_check.sh — 되살려 보지 않은 백업은 백업이 아니라 파일이다 (20장)
#
#   ./restore_check.sh /mnt/backup/rag/small_20260903_0300.dump
#
# 하는 일: 임시 데이터베이스를 하나 만들어 거기에 되살리고, 표와 줄 수를 세고, 지운다.
#          운영 데이터베이스는 건드리지 않는다.
# 한 달에 한 번. 이것이 백업 절차의 절반이다.
set -uo pipefail        # -e 를 쓰지 않는다: pg_restore 의 무해한 경고에 죽지 않도록

DUMP="${1:-}"
[ -z "$DUMP" ] && { echo "쓰는 법: $0 <덤프파일>"; exit 1; }
[ -f "$DUMP" ] || { echo "그런 파일이 없다: $DUMP"; exit 1; }

PG_ADMIN_DSN="${PG_ADMIN_DSN:-postgresql://postgres@localhost:5432/postgres}"
TMPDB="restore_check_$(date +%s)"

echo "=== 1. 덤프 파일 ================================================="
ls -lh "$DUMP"
echo "덤프가 담고 있는 것:"
pg_restore -l "$DUMP" 2>/dev/null | grep -E "TABLE DATA" | awk '{print "  -", $NF}' | head -20 || true

echo; echo "=== 2. 임시 DB 에 되살린다 ($TMPDB) ==============================="
cleanup() { psql "$PG_ADMIN_DSN" -q -c "DROP DATABASE IF EXISTS $TMPDB;" >/dev/null 2>&1 || true; }
trap cleanup EXIT
if ! psql "$PG_ADMIN_DSN" -q -c "CREATE DATABASE $TMPDB;"; then
  echo "임시 DB 를 만들지 못했다. PG_ADMIN_DSN 권한을 확인하라."; exit 1
fi
TMP_DSN="${PG_ADMIN_DSN%/*}/$TMPDB"

START=$(date +%s)
if pg_restore -d "$TMP_DSN" --no-owner --no-privileges "$DUMP" 2>/tmp/restore_err.txt; then
  echo "→ 되살아났다 ($(( $(date +%s) - START ))초)"
else
  echo "→ ⚠ 오류가 있었다. 마지막 다섯 줄:"; tail -5 /tmp/restore_err.txt
  echo "   (일부 오류는 소유자·권한 관련으로 무해하다. 아래 줄 수를 보고 판단하라.)"
fi

echo; echo "=== 3. 실제로 들어 있는가 ========================================"
psql "$TMP_DSN" -q -c "
SELECT relname AS 표, n_live_tup AS 대략_줄수
FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 15;"

EMPTY=$(psql "$TMP_DSN" -tAc "SELECT count(*) FROM pg_stat_user_tables WHERE n_live_tup = 0;")
TOTAL=$(psql "$TMP_DSN" -tAc "SELECT count(*) FROM pg_stat_user_tables;")
echo "표 $TOTAL 개 중 빈 표 $EMPTY 개"
[ "$EMPTY" = "$TOTAL" ] && echo "⚠ 전부 비었다 — 이 백업은 쓸 수 없다."

echo; echo "=== 4. 임시 DB 는 지운다 ========================================="
echo "(스크립트가 끝나면 자동으로 지운다)"
echo
echo "여기까지 통과해야 백업이다. 통과하지 못하면 그것은 파일일 뿐이다."
