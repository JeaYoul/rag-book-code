#!/usr/bin/env bash
# 불사조를 띄운다 (14장). Spark2 에서 실행.
#
#   ./run_parser.sh            # 띄운다
#   docker logs -f parser      # 죽고 되살아나는 리듬을 지켜본다
#   docker stop parser         # 손으로 멈춘다 (이때만 다시 뜨지 않는다)
set -euo pipefail
cd "$(dirname "$0")"

PAPERS="${PAPERS:-/data/papers}"       # 받아 둔 nxml · pdf (10장)
PACKAGES="${PACKAGES:-/data/packages}" # 뽑아낸 패키지 · _DONE 체크포인트

docker build -t rag-parser:latest .

docker rm -f parser 2>/dev/null || true
docker run -d --name parser \
  --gpus all \
  --shm-size=16g \
  --restart unless-stopped \
  -v "$PAPERS":/papers \
  -v "$PACKAGES":/packages \
  rag-parser:latest

echo "떴다. docker logs -f parser 로 지켜보라."
