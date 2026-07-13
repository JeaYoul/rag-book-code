"""
4장. 잘 되고 있는 걸 어떻게 아는가 — 내 RAG를 채점하기
《산골 농부의 RAG》 예제 코드

느낌은 속는다. 숫자는 속이지 않는다.

"검색 몇 번 해보니 그럴듯하네"는 검증이 아니라 기분이다.
객관적으로 채점하려면, 시스템에게 시험을 보게 해야 한다.

  ① 문제지를 만든다      — 질문과 모범 답
  ② 시스템에게 풀게 한다  — 1장에서 만든 RAG로
  ③ 네 가지 항목으로 채점한다

RAGAS 같은 도구가 하는 일이 바로 이것이다.
이름은 거창하지만, 하는 일은 시험 감독관이다.

[준비]
    ollama pull bge-m3
    ollama pull qwen2.5:3b
    pip install ollama numpy

[실행]
    python evaluate_rag.py
"""

import ollama
import numpy as np


# ─────────────────────────────────────────────
# 평가할 대상 — 1장에서 만든 그 RAG
# ─────────────────────────────────────────────
documents = [
    "브로콜리새싹에는 설포라판의 전구체인 글루코라파닌이 풍부하게 들어 있다.",
    "설포라판은 Nrf2 경로를 활성화해 항산화 효소의 발현을 높인다.",
    "낙산균은 대장에서 단쇄지방산인 부티레이트를 생성한다.",
    "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가진다.",
    "담양은 대한민국 전라남도에 있는 지역이다.",
]


def embed(text):
    return ollama.embeddings(model="bge-m3", prompt=text)["embedding"]


def search(question, doc_vectors, k=2):
    q_vec = embed(question)
    scores = [
        np.dot(q_vec, d) / (np.linalg.norm(q_vec) * np.linalg.norm(d))
        for d in doc_vectors
    ]
    top_k = np.argsort(scores)[::-1][:k]
    return [documents[i] for i in top_k]


def ask(question, doc_vectors):
    found = search(question, doc_vectors)
    prompt = f"""다음 자료만 근거로 질문에 답하세요.
자료에 없는 내용은 "자료에 없습니다"라고 답하세요.

[자료]
{chr(10).join(found)}

[질문]
{question}
"""
    answer = ollama.chat(model="qwen2.5:3b", messages=[
        {"role": "user", "content": prompt}
    ])["message"]["content"]
    return found, answer


# ─────────────────────────────────────────────
# ① 문제지 — 시험 문제와 모범 답
# ─────────────────────────────────────────────
# 여기가 평가의 출발점이다. 정답을 미리 정해두어야 채점할 수 있다.
#
# 마지막 문제를 눈여겨보라. 자료에 없는 것을 일부러 물었다.
# 시스템이 "모른다"고 답하는가, 아니면 그럴듯하게 지어내는가?
# 이것이 가장 중요한 시험이다.
TEST_SET = [
    {
        "question": "설포라판과 부티레이트의 공통점은?",
        "ground_truth": "둘 다 HDAC 억제 활성을 가진다.",
        "expected_doc": "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가진다.",
    },
    {
        "question": "브로콜리새싹에 들어있는 설포라판의 전구체는?",
        "ground_truth": "글루코라파닌이다.",
        "expected_doc": "브로콜리새싹에는 설포라판의 전구체인 글루코라파닌이 풍부하게 들어 있다.",
    },
    {
        "question": "설포라판의 하루 권장 섭취량은 몇 mg인가?",   # ← 자료에 없는 질문!
        "ground_truth": "자료에 없음",
        "expected_doc": None,
    },
]


# ─────────────────────────────────────────────
# ③ 채점 — 네 가지를 따로 본다
# ─────────────────────────────────────────────
# 핵심은 "몇 점이냐"가 아니라 "무엇을 채점하느냐"다.
# 뭉뚱그려 "괜찮네"가 아니라, RAG의 두 단계를 나눠서 본다.
#
#   [검색 단계]
#     · 꼭 필요한 자료를 찾아왔는가?   (놓치지 않았는가)
#     · 엉뚱한 자료를 물어오진 않았는가? (오염되지 않았는가)
#   [생성 단계]
#     · 자료에 없는 것을 지어내진 않았는가?  ← 가장 무서운 항목
#     · 질문에 실제로 답했는가?
#
# 실전에서는 RAGAS가 LLM을 심판으로 세워 이 채점을 자동화한다.
# 하지만 원리는 정확히 이것이다.
def evaluate(case, found_docs, answer):
    scores = {}

    # [검색] 필요한 자료를 찾아왔는가
    if case["expected_doc"]:
        scores["검색: 필요한 자료를 찾았나"] = case["expected_doc"] in found_docs
    else:
        scores["검색: 필요한 자료를 찾았나"] = None   # 애초에 자료가 없는 질문

    # [검색] 엉뚱한 자료가 섞이지 않았나 (담양 문장이 딸려왔는지)
    noise = "담양은 대한민국 전라남도에 있는 지역이다."
    scores["검색: 엉뚱한 자료가 없나"] = noise not in found_docs

    # [생성] 지어내지 않았나 — 자료에 없으면 모른다고 해야 한다
    if case["ground_truth"] == "자료에 없음":
        admitted = any(w in answer for w in ["없습니다", "없음", "알 수 없", "모르"])
        scores["생성: 지어내지 않았나"] = admitted
    else:
        scores["생성: 지어내지 않았나"] = True   # (실전에선 LLM 심판이 판정)

    # [생성] 질문에 답했나 — 모범 답의 핵심어가 들어 있는가
    if case["ground_truth"] != "자료에 없음":
        keyword = case["ground_truth"].replace(".", "").split()[0]
        scores["생성: 질문에 답했나"] = keyword in answer
    else:
        scores["생성: 질문에 답했나"] = None

    return scores


# ─────────────────────────────────────────────
# 실행 — 시험을 치르고 채점표를 받는다
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("문서를 벡터로 변환하는 중...\n")
    doc_vectors = [embed(doc) for doc in documents]

    all_scores = []

    for i, case in enumerate(TEST_SET, 1):
        found, answer = ask(case["question"], doc_vectors)
        scores = evaluate(case, found, answer)
        all_scores.append(scores)

        print("=" * 60)
        print(f"[문제 {i}] {case['question']}")
        print(f"  모범답: {case['ground_truth']}")
        print(f"  시스템: {answer.strip()[:70]}...")
        print("  ── 채점 ──")
        for item, ok in scores.items():
            mark = "—" if ok is None else ("✅" if ok else "❌")
            print(f"     {mark} {item}")
        print()

    # 항목별 총점
    print("=" * 60)
    print("최종 채점표")
    print("=" * 60)
    items = all_scores[0].keys()
    for item in items:
        vals = [s[item] for s in all_scores if s[item] is not None]
        if vals:
            rate = sum(vals) / len(vals) * 100
            print(f"  {item}: {rate:.0f}점  ({sum(vals)}/{len(vals)})")

    print()
    print("-" * 60)
    print("점수가 낮은 항목이 곧 고쳐야 할 곳이다.")
    print("  · '엉뚱한 자료' 점수가 낮다면  → 검색을 손봐야 한다 (5장)")
    print("  · '지어내지 않았나'가 낮다면   → 프롬프트를 단단히 해야 한다")
    print()
    print("측정하지 않으면 개선할 수 없다.")
    print("눈으로 '괜찮아 보인다'가 가장 위험한 판단이다.")
