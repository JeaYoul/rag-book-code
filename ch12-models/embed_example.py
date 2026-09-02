#!/usr/bin/env python3
"""
embed_example.py — bge-m3로 글을 벡터로 (12장)

이 장의 규칙 하나를 눈으로 확인하는 예제:

    ★ 넣을 때와 찾을 때, 반드시 같은 임베딩 모델을 써야 한다.

논문을 A모델로 벡터로 만들어 저장해 놓고 질문은 B모델로 만들면,
두 벡터는 서로 다른 언어로 적힌 좌표가 된다. 뜻이 같아도 가까워지지 않는다.

실행:
    pip install FlagEmbedding numpy
    python3 embed_example.py
"""
import numpy as np
from FlagEmbedding import BGEM3FlagModel

# ── 모델 ──────────────────────────────────────────────
# 11장 스키마의 vector(1024) 의 1024가 바로 이 모델에서 나온 숫자다.
MODEL_NAME = "BAAI/bge-m3"
USE_FP16 = True          # 메모리 절약. 품질 차이는 거의 없다.

print(f"모델 로딩: {MODEL_NAME}")
model = BGEM3FlagModel(MODEL_NAME, use_fp16=USE_FP16)


def embed(texts):
    """문장 목록 → 벡터 목록 (dense)"""
    out = model.encode(texts, batch_size=8, max_length=8192)
    return out["dense_vecs"]


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    # 1장의 그 작은 지식 베이스
    documents = [
        "브로콜리새싹에는 설포라판의 전구체인 글루코라파닌이 풍부하게 들어 있다.",
        "설포라판은 Nrf2 경로를 활성화해 항산화 효소의 발현을 높인다.",
        "낙산균은 대장에서 단쇄지방산인 부티레이트를 생성한다.",
        "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가진다.",
        "담양은 대한민국 전라남도에 있는 지역이다.",
    ]

    doc_vecs = embed(documents)
    print(f"\n벡터 차원: {doc_vecs.shape[1]}   ← 스키마의 vector(N) 과 같아야 한다\n")

    question = "설포라판과 부티레이트의 공통점은?"
    q_vec = embed([question])[0]

    scored = sorted(
        ((cosine(q_vec, v), d) for v, d in zip(doc_vecs, documents)),
        reverse=True,
    )

    print(f"질문: {question}\n")
    for score, doc in scored:
        print(f"  {score:.4f}  {doc}")

    print("\n※ 담양 문장이 가장 아래로 밀린 것을 확인하세요.")
    print("※ 한국어 질문 ↔ 영어 문장도 같은 공간에 놓입니다 (다국어 모델).")

    # ── 다국어 확인 (선택) ────────────────────────────
    en = "Sulforaphane and butyrate both exhibit HDAC inhibitory activity."
    en_vec = embed([en])[0]
    print(f"\n한국어 질문 ↔ 영어 문장 유사도: {cosine(q_vec, en_vec):.4f}")
