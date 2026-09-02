#!/usr/bin/env bash
#
# serve_llm.sh — Spark1에서 vLLM으로 LLM을 띄우는 실행 스크립트
#
# 9장 "모델 서빙" 절 참고.
#   - 양자화된 모델을 고른다 (직접 양자화하지 않는다)
#   - Speculative Decoding으로 좁은 메모리 대역폭을 보완한다
#   - 추측 토큰 수는 조심스럽게 조율한다 (너무 많으면 오히려 느려짐)
#
# ⚠️ 아래 <...> 자리를 당신의 실제 값으로 바꾸세요.

set -euo pipefail

# ── 1. 어떤 모델을 띄울지 ────────────────────────────────
# 이미 양자화되어 공개된 모델의 경로 또는 이름.
# 예: 로컬 경로 "/models/<your-quantized-model>" 또는 허브 이름.
MODEL="<여기에_양자화된_모델_경로_또는_이름>"

# ── 2. 어디로 서비스할지 ────────────────────────────────
HOST="0.0.0.0"          # 두 대가 서로 접근하려면 0.0.0.0
PORT="8000"             # Spark2에서 http://192.168.10.50:8000 으로 접속

# ── 3. 메모리·컨텍스트 ─────────────────────────────────
# 통합 메모리 128GB에서, 모델이 다 먹지 않고 "여유"를 남기도록 조절.
GPU_MEM_UTIL="0.90"     # 0.85~0.92 사이에서 자기 모델에 맞게
MAX_MODEL_LEN="<예: 32768>"   # 모델과 용도에 맞는 최대 컨텍스트 길이

# ── 4. Speculative Decoding (선택) ─────────────────────
# 작고 빠른 초안 모델이 다음 토큰 몇 개를 미리 추측 → 큰 모델은 검사만.
# 좁은 대역폭에서 속도를 높인다. 추측 개수는 1부터 올려보며 안정점을 찾는다.
# (9장 사례: 2 → 1 로 내렸을 때 가장 안정적이었다)
SPEC_MODEL="<선택: 초안용_작은_모델_또는_비움>"
NUM_SPEC_TOKENS="1"     # 1부터 시작 권장

# ── 실행 ───────────────────────────────────────────────
# 주의: vLLM 버전에 따라 옵션 이름이 다를 수 있습니다.
#       설치된 버전 기준으로 `vllm serve --help`를 확인하세요.

EXTRA_ARGS=()
if [[ "${SPEC_MODEL}" != "<선택: 초안용_작은_모델_또는_비움>" && -n "${SPEC_MODEL}" ]]; then
  EXTRA_ARGS+=(--speculative-model "${SPEC_MODEL}")
  EXTRA_ARGS+=(--num-speculative-tokens "${NUM_SPEC_TOKENS}")
fi

exec vllm serve "${MODEL}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  "${EXTRA_ARGS[@]}"
