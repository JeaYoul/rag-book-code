#!/usr/bin/env bash
# 불사조를 띄운다 (14장). 실제로 돌린 auto_parse.sh 의 뼈대다.
#
#   ./run_parser.sh              # 띄운다 (앞에서 계속 돈다 — nohup 이나 tmux 안에서)
#   Ctrl+C                       # 멈춘다 (trap 이 죽은 배를 치운다)
#
# 원리: 셸의 while true 가 바깥에 있고, 그 안에서 docker run --rm 으로 매번 새 컨테이너를 띄운다.
#       컨테이너가 죽든 끝나든 --rm 이 그 자리에서 지우고, 30초 뒤 같은 이미지에서 새 배가 뜬다.
#       메모리는 배와 함께 가라앉고, -v 로 붙인 볼륨의 논문·결과·체크포인트는 남는다.
set -uo pipefail
cd "$(dirname "$0")"

NAME="${NAME:-parser}"
IMAGE="${IMAGE:-rag-parser:latest}"
PAPERS="${PAPERS:-/data/papers}"          # 받아 둔 nxml · pdf (10장)
PACKAGES="${PACKAGES:-/data/packages}"    # 뽑아낸 패키지 · parsing_checkpoint.json

cleanup() {                               # 죽은 배를 확실히 치운다
    docker kill "$NAME" 2>/dev/null
    docker rm -f "$NAME" 2>/dev/null
    sleep 5
}
trap cleanup EXIT

docker build -t "$IMAGE" .

while true; do
    echo "$(date): === 파싱 시작 ==="
    cleanup
    docker run --rm --name "$NAME" \
      --gpus all \
      --shm-size=32g \
      --ulimit memlock=-1 \
      -e NCCL_P2P_DISABLE=1 -e NCCL_IB_DISABLE=1 -e NCCL_SHM_DISABLE=1 \
      -v "$PAPERS":/papers \
      -v "$PACKAGES":/packages \
      "$IMAGE" \
      python phoenix_loop.py --papers /papers --packages /packages --exit-after 80
    echo "$(date): 종료, 30초 후 재시작..."
    sleep 30
done
