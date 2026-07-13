"""
1장. 5분 만에 돌아가는 가장 단순한 RAG
《산골 농부의 RAG》 예제 코드

RAG의 전부는 두 단계다: "먼저 찾고(검색), 그다음 답한다(생성)."
이 파일은 그 두 단계를 30줄로 보여준다. 벡터 데이터베이스도, 프레임워크도 없다.

[준비]
    ollama pull bge-m3        # 임베딩용 (약 1.2GB)
    ollama pull qwen2.5:3b    # 생성용   (약 1.9GB)
    pip install ollama numpy

[실행]
    python simple_rag.py
"""

import ollama
import numpy as np


# ─────────────────────────────────────────────
# ① 우리의 "책" — 아주 작은 지식 베이스
# ─────────────────────────────────────────────
# 진짜 시스템은 논문 수천 편을 다루지만, 원리를 보는 데는 다섯 문장이면 충분하다.
# 마지막 문장(담양)은 일부러 심어둔 '엉뚱한 문장'이다. 검색이 이걸 걸러내는지 보라.
documents = [
    "브로콜리새싹에는 설포라판의 전구체인 글루코라파닌이 풍부하게 들어 있다.",
    "설포라판은 Nrf2 경로를 활성화해 항산화 효소의 발현을 높인다.",
    "낙산균은 대장에서 단쇄지방산인 부티레이트를 생성한다.",
    "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가진다.",
    "담양은 대한민국 전라남도에 있는 지역이다.",
]


# ─────────────────────────────────────────────
# ② 글을 벡터로 바꾸기 (임베딩)
# ─────────────────────────────────────────────
# 컴퓨터는 "설포라판"과 "브로콜리"가 비슷한 뜻인지 글자만 봐서는 모른다.
# 그래서 문장을 '의미를 담은 숫자 목록(벡터)'으로 바꾼다.
# 뜻이 비슷한 문장은 벡터도 비슷해진다.
def embed(text):
    res = ollama.embeddings(model="bge-m3", prompt=text)
    return res["embedding"]


# ─────────────────────────────────────────────
# ③ 질문과 가장 비슷한 문서 찾기 (검색 = Retrieval)
# ─────────────────────────────────────────────
# RAG의 첫 단계. 놀랄 만큼 단순하다.
# 벡터 데이터베이스는 아직 등장하지 않는다 — 검색이란 결국
# "숫자 목록끼리 얼마나 비슷한지 재는 것"일 뿐임을 직접 보기 위해서다.
def search(question, doc_vectors, k=2):
    q_vec = embed(question)
    scores = []
    for doc_vec in doc_vectors:
        # 코사인 유사도: 두 벡터가 같은 방향을 볼수록 1에 가까워진다
        sim = np.dot(q_vec, doc_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(doc_vec))
        scores.append(sim)
    top_k = np.argsort(scores)[::-1][:k]   # 점수 높은 순으로 상위 k개
    return [documents[i] for i in top_k]


# ─────────────────────────────────────────────
# ④ 찾은 문서를 근거로 답 만들기 (생성 = Generation)
# ─────────────────────────────────────────────
# "이 자료만 보고 답해" — 이 한 줄이 폐쇄형 시험을 오픈북 시험으로 바꾼다.
# LLM이 기억으로 지어내는 대신, 우리가 준 자료를 읽고 답하게 된다.
def ask(question, doc_vectors):
    found = search(question, doc_vectors)
    context = "\n".join(found)

    prompt = f"""다음 자료만 근거로 질문에 답하세요.

[자료]
{context}

[질문]
{question}
"""
    res = ollama.chat(model="qwen2.5:3b", messages=[
        {"role": "user", "content": prompt}
    ])
    return found, res["message"]["content"]


# ─────────────────────────────────────────────
# ⑤ 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("문서를 벡터로 변환하는 중...")
    doc_vectors = [embed(doc) for doc in documents]   # 미리 한 번만 만들어 둔다

    question = "설포라판과 부티레이트의 공통점은?"
    found, answer = ask(question, doc_vectors)

    print(f"\n[질문] {question}")

    print("\n[검색된 자료]")
    for i, doc in enumerate(found, 1):
        print(f"  {i}. {doc}")

    print(f"\n[답변]\n{answer}")

    # 눈여겨볼 것 두 가지:
    #   1. 답이 '자료'에서 나왔다. LLM이 지어낸 게 아니다.  → 환각이 줄어드는 원리
    #   2. 담양 문장은 딸려오지 않았다. 의미가 멀어 검색에서 걸러졌다. → 검색이 하는 일
