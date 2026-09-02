# 클로드 코드의 시선을 내 방의 게이트웨이로 돌린다.
# 쓰는 법:  source env.sh    (실행이 아니라 source. 새 터미널마다 다시 해야 한다.)
#
# 계속 쓰려면 ~/.bashrc 나 ~/.claude/settings.json 의 "env" 항목에 적어 둔다.

GATEWAY_HOST="${GATEWAY_HOST:-192.168.10.51}"   # Spark2
GATEWAY_PORT="${GATEWAY_PORT:-4000}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 하나 — 주소. 반드시 http:// 부터.
export ANTHROPIC_BASE_URL="http://${GATEWAY_HOST}:${GATEWAY_PORT}"

# 둘 — 열쇠. 게이트웨이용은 AUTH_TOKEN (Authorization: Bearer 로 실려 간다).
#       litellm_config.yaml 의 master_key, 즉 .env 의 LITELLM_MASTER_KEY 와 같은 값.
if [[ -z "${ANTHROPIC_AUTH_TOKEN:-}" && -f "${HERE}/.env" ]]; then
  ANTHROPIC_AUTH_TOKEN="$(grep '^LITELLM_MASTER_KEY=' "${HERE}/.env" | cut -d= -f2-)"
fi
export ANTHROPIC_AUTH_TOKEN

# 셋 — 원래 서비스용 열쇠는 지운다. 둘이 같이 있으면 엉킨다 (401).
unset ANTHROPIC_API_KEY

# 넷 — 어떤 이름을 불러도 qwen 으로.
export ANTHROPIC_MODEL="qwen"
export ANTHROPIC_SMALL_FAST_MODEL="qwen"

# 확인
echo "ANTHROPIC_BASE_URL   = ${ANTHROPIC_BASE_URL}"
if [[ -n "${ANTHROPIC_AUTH_TOKEN}" ]]; then
  echo "ANTHROPIC_AUTH_TOKEN = (설정됨)"
else
  echo "ANTHROPIC_AUTH_TOKEN = (비어 있음! .env 를 확인하라)"
fi
echo "ANTHROPIC_API_KEY    = (지워짐, 정상)"
echo "ANTHROPIC_MODEL      = ${ANTHROPIC_MODEL}"
echo "이제 claude 를 치고, 안에서 /status 로 주소를 확인하라."
