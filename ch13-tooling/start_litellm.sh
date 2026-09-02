#!/usr/bin/env bash
# 게이트웨이를 띄운다. Spark2에서 실행.
set -euo pipefail
cd "$(dirname "$0")"

# .env 에서 LITELLM_MASTER_KEY 를 읽는다
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
: "${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY 가 없다. .env.example 을 .env 로 복사하고 값을 넣어라.}"

PORT="${LITELLM_PORT:-4000}"

# 다섯 번째 자리 — 포트가 이미 쓰이고 있는가
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${PORT}$"; then
  echo "[!] ${PORT} 포트가 이미 쓰이고 있다. LITELLM_PORT 로 다른 번호를 줘라." >&2
  ss -ltnp 2>/dev/null | grep ":${PORT}" >&2 || true
  exit 1
fi

exec litellm --config litellm_config.yaml --host 0.0.0.0 --port "$PORT"
