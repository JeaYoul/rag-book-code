#!/usr/bin/env python3
"""
rerank_distribution.py — 리랭커 점수가 어떻게 퍼져 있나, 문턱을 어디에 둘까 (17장 "근거 정밀도")

    python rerank_distribution.py results/open.json [--threshold 0.35]

실제로 한 시험에서 점수가 0.22~0.80 에 퍼져 있었고 아래 절반이 잡음이었다. 그래서 0.35 아래는 버렸다.
문턱을 넘는 것이 셋 미만이면 점수 순으로 셋은 남긴다 — 아무것도 안 남는 것보다 낫다.
"""
import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")


def apply_threshold(chunks, threshold=0.35, min_keep=3):
    ranked = sorted(chunks, key=lambda c: c.get("rerank_score") or 0, reverse=True)
    kept = [c for c in ranked if (c.get("rerank_score") or 0) >= threshold]
    fallback = len(kept) < min_keep
    return (ranked[:min_keep] if fallback else kept), fallback


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path)
    ap.add_argument("--threshold", type=float, default=0.35)
    a = ap.parse_args()

    d = json.loads(a.results.read_text(encoding="utf-8"))
    scores = [c["rerank_score"] for r in d["results"] for c in r.get("contexts", []) if c.get("rerank_score") is not None]
    if not scores:
        print("rerank_score 가 없다 — open 모드 결과 파일을 주어라"); return 1
    scores.sort()
    print(f"조각 {len(scores)}개 · 최소 {scores[0]:.3f} · 중앙 {scores[len(scores)//2]:.3f} · 최대 {scores[-1]:.3f}")
    print("분포 (0.1 칸):")
    for lo in [i / 10 for i in range(10)]:
        n = sum(1 for s in scores if lo <= s < lo + 0.1 or (lo == 0.9 and s == 1.0))
        print(f"  {lo:.1f}~{lo+0.1:.1f} {'█' * n} {n}")
    below = sum(1 for s in scores if s < a.threshold)
    print(f"\n문턱 {a.threshold}: 아래 {below}개 버림 · 위 {len(scores)-below}개 남김")
    fb = sum(1 for r in d["results"] if apply_threshold(r.get("contexts", []), a.threshold)[1])
    print(f"최소 3편 안전망 발동: {fb}/{len(d['results'])} 문항")
    return 0


if __name__ == "__main__":
    sys.exit(main())
