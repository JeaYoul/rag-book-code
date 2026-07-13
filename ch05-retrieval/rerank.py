"""
5장. 검색이 헛다리를 짚던 밤 — 리랭커
《산골 농부의 RAG》 예제 코드

답이 부실한 건 대개 LLM 탓이 아니다.
애초에 엉뚱한 자료를 쥐여준 검색 탓이다.

  RAG의 품질은 검색의 품질을 넘지 못한다.

이 코드는 검색의 2단 구조를 보여준다.

  ① 벡터 검색 — 수백만 개에서 후보를 빠르게 건진다 (빠르지만 거칠다)
  ② 리랭커    — 그 후보만 꼼꼼히 다시 본다        (느리지만 정확하다)

수백만 개를 전부 꼼꼼히 볼 수는 없다. 하지만 스무 개라면 볼 수 있다.
빠른 그물로 건지고, 정밀한 손으로 고른다.

[준비]
    ollama pull bge-m3
    ollama pull qwen2.5:3b     # 여기서는 리랭커 심판 역할도 겸한다
    pip install ollama numpy

[실행]
    python rerank.py
"""

import ollama
import numpy as np


# ─────────────────────────────────────────────
# 지식 베이스 — 일부러 '헷갈리게' 만들었다
# ─────────────────────────────────────────────
# 벡터 검색이 헛다리를 짚는 상황을 보려면, 함정이 필요하다.
# 아래 문장들은 전부 '설포라판'이라는 단어를 품고 있다.
# 단어만 보면 다 비슷해 보이지만, 질문에 대한 '진짜 답'은 하나뿐이다.
documents = [
    "설포라판은 브로콜리, 양배추 등 십자화과 채소에 들어 있다.",
    "설포라판의 화학식은 C6H11NOS2이며 분자량은 177.29이다.",
    "설포라판은 Nrf2 경로를 활성화해 항산화 효소의 발현을 높인다.",
    "설포라판 연구는 1990년대 존스홉킨스 대학에서 본격화되었다.",
    "설포라판은 열에 약해 조리 시 상당량이 파괴된다.",
    "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가지며, 병용 시 시너지를 낸다.",
    "설포라판 보충제 시장은 최근 빠르게 성장하고 있다.",
    "브로콜리새싹은 성숙한 브로콜리보다 설포라판 전구체를 훨씬 많이 함유한다.",
]

QUESTION = "설포라판과 부티레이트를 함께 쓰면 어떻게 되는가?"


def embed(text):
    return ollama.embeddings(model="bge-m3", prompt=text)["embedding"]


# ─────────────────────────────────────────────
# ① 벡터 검색 — 빠르지만 거칠다
# ─────────────────────────────────────────────
# 질문과 문서를 '따로따로' 벡터로 만들어 비교한다.
# 그래서 빠르다 (문서 벡터는 미리 만들어두면 되니까).
# 하지만 거칠다 — 단어가 비슷하기만 해도 딸려온다.
def vector_search(question, doc_vectors, k=4):
    q_vec = embed(question)
    scores = []
    for d in doc_vectors:
        sim = np.dot(q_vec, d) / (np.linalg.norm(q_vec) * np.linalg.norm(d))
        scores.append(sim)

    top_k = np.argsort(scores)[::-1][:k]
    return [(documents[i], scores[i]) for i in top_k]


# ─────────────────────────────────────────────
# ② 리랭커 — 느리지만 정확하다
# ─────────────────────────────────────────────
# 벡터 검색과 결정적으로 다른 점:
#   벡터 검색 → 질문과 문서를 '따로' 벡터로 만들어 비교
#   리랭커    → 질문과 문서를 '나란히 놓고 함께' 들여다본다
#
# 함께 보기 때문에 정확하다. 대신 문서 하나하나를 다시 봐야 해서 느리다.
# 그래서 수백만 개가 아니라, 벡터 검색이 건져 온 '후보'에게만 쓴다.
#
# 실전에서는 전용 리랭커 모델(Qwen3-Reranker 등)을 쓴다.
# 여기서는 원리를 보여주기 위해 LLM에게 심판을 맡긴다.
def rerank(question, candidates, k=2):
    scored = []

    for doc, _ in candidates:
        prompt = f"""아래 문서가 질문에 답하는 데 얼마나 도움이 되는지 0에서 10 사이 숫자로만 답하세요.
숫자 외에는 아무것도 쓰지 마세요.

[질문] {question}
[문서] {doc}

점수:"""
        res = ollama.chat(model="qwen2.5:3b", messages=[
            {"role": "user", "content": prompt}
        ])["message"]["content"]

        # 답에서 숫자만 뽑아낸다
        try:
            score = float("".join(c for c in res if c.isdigit() or c == ".")[:4])
        except ValueError:
            score = 0.0

        scored.append((doc, min(score, 10.0)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


# ─────────────────────────────────────────────
# 실행 — 리랭커가 있고 없고의 차이를 눈으로 본다
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("문서를 벡터로 변환하는 중...\n")
    doc_vectors = [embed(d) for d in documents]

    print("=" * 65)
    print(f"질문: {QUESTION}")
    print("=" * 65)

    # ── 1단계: 벡터 검색 (빠른 그물)
    candidates = vector_search(QUESTION, doc_vectors, k=4)

    print("\n【1단계】 벡터 검색이 건져 온 후보 4개 (빠르지만 거칠다)")
    print("-" * 65)
    for i, (doc, score) in enumerate(candidates, 1):
        print(f"  {i}위 (유사도 {score:.3f})  {doc}")

    # ── 2단계: 리랭커 (정밀한 손)
    print("\n【2단계】 리랭커가 후보만 꼼꼼히 다시 본다 (느리지만 정확하다)")
    print("-" * 65)
    final = rerank(QUESTION, candidates, k=2)
    for i, (doc, score) in enumerate(final, 1):
        print(f"  {i}위 (관련도 {score:.1f}/10)  {doc}")

    # ── 비교
    print("\n" + "=" * 65)
    print("무엇이 달라졌나")
    print("=" * 65)

    before_top = candidates[0][0]
    after_top = final[0][0]

    print(f"  벡터 검색 1위 : {before_top}")
    print(f"  리랭킹 후 1위 : {after_top}")
    print()

    if before_top != after_top:
        print("  → 순위가 바뀌었다!")
        print("     벡터 검색은 '설포라판'이라는 단어가 비슷하기만 해도 딸려온다.")
        print("     리랭커는 질문과 문서를 함께 보고, 진짜 답을 위로 올린다.")
    else:
        print("  → 이번엔 순위가 같다. (문서가 8개뿐이라 벡터 검색만으로도 충분했다)")
        print("     하지만 수백만 조각이라면 이야기가 다르다.")
        print("     후보 안에 정답이 있어도, 1위가 아니면 LLM은 그것을 못 본다.")

    print()
    print("-" * 65)
    print("핵심은 역할 분담이다.")
    print("  수백만 개를 전부 꼼꼼히 볼 수는 없다 — 영원히 걸린다.")
    print("  하지만 벡터 검색이 20개로 줄여주면, 그 20개는 꼼꼼히 볼 수 있다.")
    print("  빠른 그물로 건지고, 정밀한 손으로 고른다.")
