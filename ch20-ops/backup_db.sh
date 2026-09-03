#!/usr/bin/env bash
# backup_db.sh — 없다고 확인한 그 백업 (20장)
#
#   ./backup_db.sh --dry-run              무엇을 뜰지만 보여 준다
#   ./backup_db.sh                        실제로 뜬다
#   0 3 * * *  /경로/backup_db.sh >> /var/log/backup_db.log 2>&1     ← 크론에 이렇게
#
# 20장에서 확인한 것:
#   · 이 명령을 부르는 스크립트가 기계에 한 건도 없었다
#   · 있는 백업은 넉 달 전에 한 번 뜬 244GB 하나와, 큰 작업 직전에 손으로 뜬 조각 몇 개
#   · 그리고 그것이 원본과 같은 디스크에 있었다 — 같은 배에 실은 구명보트
#
# 그래서 이 스크립트의 규칙은 넷이다.
#   1) 다른 디스크에 둔다 (BACKUP_DIR 을 다른 장치로. 안 되면 최소한 다른 기계로 복사)
#   2) 자동으로 돈다 (크론)
#   3) 다시 만들 수 없는 것만 매일 뜬다 (전체는 주 1회)
#   4) 뜬 다음 되살아나는지 확인한다 (restore_check.sh)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/mnt/backup/rag}"       # ← 반드시 다른 디스크로 바꿔라
KEEP_DAYS="${KEEP_DAYS:-14}"
PG_DSN="${PG_DSN:-}"
STAMP=$(date +%Y%m%d_%H%M)
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

log() { echo "[$(date '+%F %T')] $*"; }
run() { if [ "$DRY" = "1" ]; then echo "  (dry-run) $*"; else eval "$*"; fi; }

if [ -z "$PG_DSN" ]; then
  echo "PG_DSN 이 없다.  export PG_DSN=postgresql://user:pw@localhost:5432/db"; exit 1
fi

# 다른 디스크인지 확인 — 같은 디스크면 백업이 아니다
SRC_DEV=$(df --output=source / | tail -1)
DST_DEV=$(df --output=source "$(dirname "$BACKUP_DIR")" 2>/dev/null | tail -1 || echo "?")
log "원본 디스크=$SRC_DEV  백업 디스크=$DST_DEV"
if [ "$SRC_DEV" = "$DST_DEV" ]; then
  log "⚠ 같은 디스크다. 디스크가 죽으면 백업도 같이 죽는다. BACKUP_DIR 을 다른 장치로 바꿔라."
  [ "${ALLOW_SAME_DISK:-0}" = "1" ] || { log "중단. 정말 이대로 하려면 ALLOW_SAME_DISK=1"; exit 2; }
fi

run "mkdir -p '$BACKUP_DIR'"

# --- 매일: 다시 만들 수 없는 것 ------------------------------------------------
# 사용자·보고서·용어사전·감사로그. 작고, 잃으면 되살릴 방법이 없다.
SMALL="$BACKUP_DIR/small_$STAMP.dump"
log "매일치: 사용자·보고서·용어사전·감사로그 → $SMALL"
run "pg_dump '$PG_DSN' -Fc -f '$SMALL' \
     -t users -t user_reports -t glossary_terms -t login_attempts -t admin_actions"

# --- 주 1회(일요일): 전체 ------------------------------------------------------
# 논문·조각·임베딩. 크지만, 다시 만들려면 며칠이 걸린다.
if [ "$(date +%u)" = "7" ] || [ "${FULL:-0}" = "1" ]; then
  FULLF="$BACKUP_DIR/full_$STAMP.dump"
  log "주간치: 전체 → $FULLF"
  run "pg_dump '$PG_DSN' -Fc -Z6 -f '$FULLF'"
else
  log "주간치: 오늘은 건너뜀 (일요일에 뜬다. 지금 뜨려면 FULL=1)"
fi

# --- 오래된 것 정리 ------------------------------------------------------------
log "$KEEP_DAYS 일 지난 것 정리"
run "find '$BACKUP_DIR' -name '*.dump' -mtime +$KEEP_DAYS -print -delete"

# --- 결과 ---------------------------------------------------------------------
if [ "$DRY" = "0" ]; then
  log "현재 백업:"
  ls -lh "$BACKUP_DIR"/*.dump 2>/dev/null | tail -5 || log "  (없음)"
  log "뜬 것으로 끝이 아니다. 한 달에 한 번 restore_check.sh 로 되살려 봐라."
fi
