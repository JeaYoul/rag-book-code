"""
2장. 죽으면 다시 살아나는 새 — 불사조 파서
《산골 농부의 RAG》 예제 코드

기계가 계속 죽는데 고칠 수 없다면?
→ 죽어도 스스로 다시 일어서게 만들면 된다.

불사조는 세 부품으로 이루어진다.
    ① 죽으면 자동으로 다시 켜지기   (재시작)
    ② 되살아날 때 메모리 비우기      (메모리 청소)
    ③ 어디까지 했는지 기억하기       (체크포인트)

이 파일은 그 세 부품을 실제로 보여준다.
실제 운영 코드는 669줄이지만, 원리는 이게 전부다.

[실행]
    python phoenix_parser.py

[불사조 체험하기]
    실행 도중 Ctrl+C 로 강제로 죽여 보라.
    다시 실행하면 — 처음부터가 아니라, 죽은 지점부터 이어간다.
    이것이 불사조다.
"""

import gc
import json
import time
import random
from pathlib import Path

# GPU를 쓴다면 torch도 함께 (없으면 이 부분은 건너뛴다)
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


CHECKPOINT_FILE = Path("checkpoint.json")   # 어디까지 했는지 기록하는 파일
BATCH_SIZE = 10                             # 몇 편마다 체크포인트를 저장할지


# ─────────────────────────────────────────────
# 부품 ② — 메모리 비우기
# ─────────────────────────────────────────────
# 기계가 자꾸 죽는 이유 중 하나는 메모리가 조금씩 눌러붙기 때문이다(메모리 누수).
# 한 편을 처리하고 나면 다 쓴 재료를 확실히 치워야, 다음 편에서 깨끗하게 시작한다.
#
# gc 는 garbage collection, 말 그대로 '쓰레기 수거'다. 이름만 알면 어렵지 않다.
def cleanup_memory():
    """GPU 및 시스템 메모리 정리"""
    gc.collect()                      # 파이썬에게 "이제 청소해" 하고 시킨다
    if HAS_TORCH and torch.cuda.is_available():
        torch.cuda.empty_cache()      # GPU 메모리도 비운다
        torch.cuda.synchronize()      # GPU 작업이 다 끝날 때까지 기다린다


# ─────────────────────────────────────────────
# 부품 ③ — 체크포인트 (어디까지 했는지 기억하기)
# ─────────────────────────────────────────────
# 죽었다 살아날 때마다 처음부터 다시 하면 영원히 끝나지 않는다.
# 그래서 처리한 것을 파일에 기록해두고, 되살아나면 그다음부터 이어간다.
def load_checkpoint():
    """체크포인트 로드 — 없으면 빈 상태로 시작"""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "failed": []}


def save_checkpoint(checkpoint):
    """체크포인트 저장"""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2)


# ─────────────────────────────────────────────
# 실제 작업 (여기서는 흉내만 낸다)
# ─────────────────────────────────────────────
# 진짜 시스템에서는 여기서 논문 한 편을 파싱한다.
# 이 예제에서는 '가끔 죽는' 상황을 흉내 내기 위해, 낮은 확률로 일부러 뻗게 했다.
def process_one(paper_id):
    """논문 한 편 처리 — 5% 확률로 크래시를 흉내 낸다"""
    time.sleep(0.3)                                  # 파싱하는 척

    if random.random() < 0.05:                       # 5% 확률로 뻗는다
        raise RuntimeError("Signal 11 — 기계가 픽 쓰러졌다")

    return {"chunks": random.randint(10, 30)}        # 처리 결과


# ─────────────────────────────────────────────
# 메인 — 세 부품을 합쳐 불사조를 완성한다
# ─────────────────────────────────────────────
def main():
    # 처리할 대상 (진짜라면 논문 수만 편)
    all_papers = [f"PMC{1000 + i}" for i in range(100)]

    # ★ 부품 ③ — 이미 처리한 것은 건너뛴다
    checkpoint = load_checkpoint()
    processed_set = set(checkpoint["processed"])

    to_process = [p for p in all_papers if p not in processed_set]

    print(f"전체: {len(all_papers)}편")
    print(f"이미 처리됨: {len(processed_set)}편  ← 죽기 전에 해둔 것")
    print(f"처리할 것: {len(to_process)}편")
    print("-" * 50)

    if not to_process:
        print("모두 처리 완료!")
        return

    for i, paper_id in enumerate(to_process, 1):
        try:
            result = process_one(paper_id)
            checkpoint["processed"].append(paper_id)
            print(f"  [{i}/{len(to_process)}] {paper_id} — 청크 {result['chunks']}개")

        except Exception as e:
            checkpoint["failed"].append({"id": paper_id, "error": str(e)})
            print(f"  [{i}/{len(to_process)}] {paper_id} — ❌ {e}")

        # ★ 부품 ② — 매 편 처리 후 메모리 청소
        cleanup_memory()

        # 배치마다 체크포인트 저장 + 잠깐 숨 고르기
        # (매 편 저장하면 느리다. 기계에도 쉴 틈을 준다.)
        if i % BATCH_SIZE == 0:
            save_checkpoint(checkpoint)
            cleanup_memory()
            print(f"  ── 배치 {i // BATCH_SIZE} 완료: 체크포인트 저장, 메모리 정리")
            time.sleep(1)

    save_checkpoint(checkpoint)   # 마지막 저장

    print("-" * 50)
    print(f"완료! 성공 {len(checkpoint['processed'])}편, 실패 {len(checkpoint['failed'])}편")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────
# 부품 ① — 죽으면 자동으로 다시 켜지기 (재시작)
# ─────────────────────────────────────────────
# 위 코드는 '되살아날 준비'가 된 파서다. 이제 죽었을 때 누가 다시 켜주느냐만 남았다.
# 방법은 두 가지. 둘 다 하는 일은 똑같다 — "죽으면 다시 켠다."
#
# 【방법 1】 셸 스크립트 — 가장 단순하다. 이게 불사조의 심장이다.
#
#     while true; do
#         python phoenix_parser.py       # 파싱을 시작한다
#         echo "종료됨. 30초 후 다시 시작..."   # 죽으면 여기로 온다
#         sleep 30                       # 잠깐 숨 고르고
#     done                               # 루프가 다시 위로 돌아간다
#
# 【방법 2】 도커 — 내가 실제로 쓴 방식. docker-compose.yml 에 한 줄이면 된다.
#
#     services:
#       parser:
#         restart: always                # 죽으면 도커가 알아서 다시 띄운다
#
# 어느 쪽이든, 파서가 죽어도 다시 켜지고 → 체크포인트를 읽어 → 멈춘 지점부터 이어간다.
# 재가 되어도 그 재에서 다시 태어나는 새. 그것이 불사조다.
