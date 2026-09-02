#!/usr/bin/env bash
# 막히는 다섯 자리를 순서대로 짚는다.
#   주소 -> 열쇠 -> 살아 있는지 -> OpenAI 형식 -> Anthropic 형식
# 어디서 멈추는지가 곧 어디가 어긋났는지다.
#
# 먼저  source env.sh  를 한 뒤 실행한다.
set -uo pipefail
cd "$(dirname "$0")"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

BASE="${ANTHROPIC_BASE_URL:-http://192.168.10.51:4000}"
KEY="${ANTHROPIC_AUTH_TOKEN:-${LITELLM_MASTER_KEY:-}}"
VLLM="${VLLM_BASE:-http://192.168.10.50:8000}"

ok()  { echo "  [OK] $*"; }
bad() { echo "  [X ] $*"; }

echo "1. 주소 형식"
if [[ "$BASE" =~ ^https?:// ]]; then
  ok "$BASE"
else
  bad "$BASE  <- http:// 가 빠졌다."
  exit 1
fi

echo "2. 열쇠"
if [[ -n "$KEY" ]]; then
  ok "ANTHROPIC_AUTH_TOKEN 있음"
else
  bad "열쇠가 비었다. source env.sh 를 했는가?"
  exit 1
fi
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  bad "ANTHROPIC_API_KEY 가 남아 있다. unset 하라 (401의 흔한 원인)."
else
  ok "ANTHROPIC_API_KEY 없음 (정상)"
fi

echo "3. 살아 있는가"
if curl -sf --max-time 5 "$VLLM/v1/models" >/dev/null; then
  ok "vLLM $VLLM"
else
  bad "vLLM 이 응답 없음. Spark1 부터 보라."
fi
if curl -sf --max-time 5 -H "Authorization: Bearer $KEY" "$BASE/v1/models" >/dev/null; then
  ok "게이트웨이 $BASE"
else
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "Authorization: Bearer $KEY" "$BASE/v1/models")
  case "$code" in
    401) bad "게이트웨이는 살아 있는데 열쇠를 거절 (401). master_key 와 AUTH_TOKEN 이 같은가?" ;;
    000) bad "연결 자체가 안 됨. 게이트웨이가 죽었거나 포트/방화벽 문제." ;;
    *)   bad "게이트웨이 응답 $code" ;;
  esac
  exit 1
fi

echo "4. OpenAI 형식으로 한 마디"
resp=$(curl -s --max-time 120 "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Reply with exactly one word: mountain"}],"max_tokens":20}')
if grep -q '"choices"' <<<"$resp"; then
  ok "$(sed -n 's/.*"content": *"\([^"]*\)".*/\1/p' <<<"$resp" | head -c 80)"
else
  bad "$resp"
  exit 1
fi

echo "5. Anthropic 형식으로 한 마디 (클로드 코드가 쓰는 길)"
resp=$(curl -s --max-time 120 "$BASE/v1/messages" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"qwen","max_tokens":20,"messages":[{"role":"user","content":"Reply with exactly one word: phoenix"}]}')
if grep -q '"content"' <<<"$resp"; then
  ok "$(sed -n 's/.*"text": *"\([^"]*\)".*/\1/p' <<<"$resp" | head -c 80)"
else
  bad "$resp"
  exit 1
fi

echo
echo "다섯 자리 모두 통과. 이제 claude 를 띄우고 /status 를 보라."
