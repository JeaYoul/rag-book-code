#!/usr/bin/env python3
"""
evaluate.py — 네 지표로 채점하고, 같은 결과 파일에 적어 둔다 (17장 "RAGAS 실전")

    python evaluate.py results/open.json            # 심판 LLM (OpenAI 호환, LLM_BASE_URL)
    python evaluate.py results/open.json --fake     # 모델 없이 낱말 겹침으로 (흐름 실습용)

네 지표 (RAGAS 의 잣대, 채점기는 직접):
    faithfulness       답을 주장(문장)으로 쪼개 → 근거가 뒷받침하는 주장 / 전체 주장
    answer_relevancy   답이 질문에 답했는가 (0~1)
    context_precision  가져온 근거 중 질문에 쓸모 있는 것의 비율
    context_recall     모범답의 요점 중 근거에서 찾을 수 있는 것의 비율
최저선: 0.60 / 0.65 / 0.50 / 0.55 — 아래면 그 칸은 낙제.

심판 모델은 시험 보는 모델과 달라야 한다. LLM_BASE_URL 을 답을 쓴 모델과 다른 곳으로 두어라.
점수는 문항마다 scores 로, 파일 머리에 scores_summary 와 채점 날짜로 덧붙인다.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

THRESHOLDS = {"faithfulness": 0.60, "answer_relevancy": 0.65, "context_precision": 0.50, "context_recall": 0.55}
LLM_BASE_URL = os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL", "http://localhost:4000/v1")
LLM_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL", "qwen")


def split_claims(text):
    text = re.sub(r"\[[^\]]*\]", "", text)                         # 인용 표시는 뺀다
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


# ---------------------------------------------------------------- 심판

class LLMJudge:
    """OpenAI 호환 심판. 0~1 숫자 하나만 받는다."""

    def _ask(self, prompt):
        import requests
        r = requests.post(f"{LLM_BASE_URL}/chat/completions", json={
            "model": LLM_MODEL, "temperature": 0, "max_tokens": 10,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": "You are a strict grader. Reply with a single number between 0 and 1 and nothing else."},
                         {"role": "user", "content": prompt}]}, timeout=60)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or "0"
        m = re.search(r"[01](?:\.\d+)?", text)
        return float(m.group(0)) if m else 0.0

    def supported(self, claim, contexts):
        return self._ask(f"Is the CLAIM fully supported by the CONTEXT? 1 = yes, 0 = no.\n\nCONTEXT:\n{contexts[:6000]}\n\nCLAIM: {claim}") >= 0.5

    def score(self, prompt):
        return self._ask(prompt)


class FakeJudge:
    """모델 없이 — 낱말 겹침. 뜻은 모른다. 흐름을 실습할 때만."""

    @staticmethod
    def _words(t):
        return set(re.findall(r"[a-zA-Z가-힣0-9]{2,}", t.lower()))

    def supported(self, claim, contexts):
        cw = self._words(claim)
        return bool(cw) and len(cw & self._words(contexts)) / len(cw) >= 0.5

    def score(self, prompt):
        # prompt 에 'A:' 와 'B:' 두 덩어리를 넣어 두면 그 둘의 겹침 비율을 돌려준다
        a = re.search(r"A:(.*?)\nB:", prompt, re.DOTALL); b = re.search(r"B:(.*)", prompt, re.DOTALL)
        wa, wb = self._words(a.group(1) if a else ""), self._words(b.group(1) if b else "")
        return round(len(wa & wb) / len(wa), 3) if wa else 0.0


# ---------------------------------------------------------------- 네 지표

def evaluate_one(r, judge):
    answer, question, gt = r.get("answer", ""), r["question"], r.get("ground_truth", "")
    ctx_texts = [c["content"] for c in r.get("contexts", [])]
    ctx_all = "\n\n".join(ctx_texts)

    claims = split_claims(answer)
    supported = [judge.supported(c, ctx_all) for c in claims] if ctx_texts else [False] * len(claims)
    faithfulness = sum(supported) / len(claims) if claims else 0.0

    relevancy = judge.score(f"How well does B answer A? 0~1.\nA:{question}\nB:{answer[:3000]}")

    useful = [judge.score(f"Is B useful evidence for answering A? 0~1.\nA:{question}\nB:{t[:2000]}") >= 0.5 for t in ctx_texts]
    precision = sum(useful) / len(useful) if useful else 0.0

    gt_points = split_claims(gt) or ([gt] if gt else [])
    found = [judge.supported(p, ctx_all) for p in gt_points] if (gt_points and ctx_texts) else []
    recall = sum(found) / len(found) if found else 0.0

    scores = {"faithfulness": round(faithfulness, 3), "answer_relevancy": round(relevancy, 3),
              "context_precision": round(precision, 3), "context_recall": round(recall, 3)}
    scores["overall"] = round(sum(scores.values()) / 4, 3)
    scores["failed"] = [k for k, v in THRESHOLDS.items() if scores[k] < v]
    scores["claims"] = len(claims)
    scores["unsupported_claims"] = [c for c, s in zip(claims, supported) if not s][:3]
    return scores


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path)
    ap.add_argument("--fake", action="store_true")
    a = ap.parse_args()
    judge = FakeJudge() if a.fake else LLMJudge()

    d = json.loads(a.results.read_text(encoding="utf-8"))
    for r in d["results"]:
        r["scores"] = evaluate_one(r, judge)
        s = r["scores"]
        print(f"[{r['id']}] F={s['faithfulness']:.2f} R={s['answer_relevancy']:.2f} "
              f"P={s['context_precision']:.2f} C={s['context_recall']:.2f} → {s['overall']:.2f}"
              + (f"  낙제: {','.join(s['failed'])}" if s["failed"] else ""))

    keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "overall"]
    summary = {k: round(sum(r["scores"][k] for r in d["results"]) / len(d["results"]), 3) for k in keys}
    summary["thresholds"] = THRESHOLDS
    summary["graded_at"] = datetime.now().isoformat(timespec="seconds")
    summary["judge"] = "fake(word-overlap)" if a.fake else f"{LLM_MODEL}@{LLM_BASE_URL}"
    d["scores_summary"] = summary
    a.results.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")   # 적어 둔다
    print("\n평균:", {k: summary[k] for k in keys}, "\n→", a.results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
