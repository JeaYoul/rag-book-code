#!/usr/bin/env python3
"""
leak_check.py — 내보내기 전에 한 번 더 본다 (23장)

    python leak_check.py --demo                    다섯 경우를 보여 준다
    python leak_check.py report.md                 파일 하나를 검사
    python leak_check.py report.md --level public   공개용으로 내보낼 때 (가장 엄격)

무엇을 하는가.
    화면에 띄우거나 문서로 내보내려는 글에, 나가면 안 되는 것이 섞여 있는지 본다.
    막지는 못한다. 사람 눈에 띄게 한다. 19장의 무인용 문단 가드와 같은 성격이다.

왜 필요한가.
    23장에서 이렇게 썼다. 책에 무엇을 쓰지 않을지 정하는 일과,
    시스템이 무엇을 내보내지 않을지 정하는 일은 같은 일이다.
    그 "정한 것"을 사람의 기억에만 두지 않으려고 코드로 옮긴 것이다.

★ 규칙은 자기 회사 것으로 바꿔야 한다.
  아래 목록은 본보기다. 실제 성분명·제품명·균주명은 이 책에 적지 않았고,
  당신 회사의 것은 당신만 안다. RULES 를 자기 것으로 채우는 것이 이 파일을 쓰는 첫 일이다.
"""
import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

# 내보내는 등급. 왼쪽이 가장 엄격하다 (밖으로 멀리 나갈수록 엄격)
#   public     … 회사 밖으로 (홈페이지 · 논문 · 이 책)
#   restricted … 거래처나 협력기관까지
#   internal   … 사내 열람용
LEVELS = ["public", "restricted", "internal"]

# (이름, 정규식, applies_upto, 설명)
#   applies_upto = 이 규칙이 걸리는 **가장 느슨한** 등급.
#   그 등급과 그보다 엄격한 등급 전부에서 걸린다.
#   예) applies_upto="internal" 이면 사내 문서에서도 걸린다 = 어디서도 안 된다.
#       applies_upto="public"  이면 공개용으로 내보낼 때만 걸린다.
RULES = [
    ("자격 증명", r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S{8,}", "internal",
     "어느 등급에서도 나가면 안 된다. 사내 문서에도 있어서는 안 된다"),
    ("배합비", r"\d+(?:\.\d+)?\s*(?:중량\s*)?(?:%|퍼센트|wt%)\s*(?:배합|함유|첨가)", "restricted",
     "배합비는 제품의 핵심이다. 수치가 하나만 나가도 역산이 시작된다"),
    ("공정 조건", r"\d+\s*(?:도|℃|°C)\s*(?:에서|,)?\s*\d+\s*(?:분|시간|hr|min)", "restricted",
     "온도와 시간의 조합은 대개 여러 번 실패한 끝에 얻은 값이다"),
    ("균주 번호", r"\b[A-Z]{2,4}\s?-?\s?\d{3,5}\b(?=.{0,20}(?:균주|strain|KCTC|KCCM))", "restricted",
     "균주 번호는 우리가 고른 결과다. 그 자체가 연구의 결론이다"),
    ("내부 문서번호", r"\b(?:NPK|INT|RND)-\d{2,}-\d{2,}\b", "restricted",
     "내부 문서번호 체계가 드러난다. 번호만으로도 규모와 이력이 추정된다"),
    ("출원 전 표시", r"(출원\s*예정|출원\s*전|미공개|대외비|사내\s*한정|CONFIDENTIAL|DO NOT DISTRIBUTE)", "restricted",
     "문서 자체가 밖으로 나가면 안 된다고 말하고 있다"),
    ("연락처", r"[\w.+-]+@[\w-]+\.[\w.]+|0\d{1,2}-\d{3,4}-\d{4}", "public",
     "사람을 특정할 수 있다. 사내에서는 문제가 없지만 공개용에서는 뺀다"),
]


def check(text, level="restricted"):
    """걸린 것 목록을 돌려준다. 자르거나 고치지 않는다 — 판단은 사람이 한다."""
    if level not in LEVELS:
        raise ValueError(f"등급은 {LEVELS} 중 하나")
    strictness = LEVELS.index(level)          # 0 = 가장 엄격
    hits = []
    for name, pattern, applies_upto, why in RULES:
        # 이 등급이 규칙의 적용 범위 안에 있는가
        if strictness > LEVELS.index(applies_upto):
            continue
        for m in re.finditer(pattern, text):
            line = text[:m.start()].count("\n") + 1
            hits.append({"rule": name, "line": line, "text": m.group(0)[:40], "why": why})
    return hits


def report(hits, level):
    if not hits:
        print(f"[{level}] 걸린 것 없음.")
        print("다만 이 검사는 규칙에 적어 둔 것만 본다. 적지 않은 것은 지나간다.")
        return 0
    print(f"[{level}] {len(hits)}건 걸렸다. 내보내기 전에 사람이 확인하라.")
    print()
    seen = set()
    for h in hits:
        print(f"  {h['line']:>4}행  {h['rule']:<12} \"{h['text']}\"")
        if h["rule"] not in seen:
            print(f"          └ {h['why']}")
            seen.add(h["rule"])
    print()
    print("이 도구는 막지 않는다. 표시할 뿐이다. 내보낼지 말지는 사람이 정한다.")
    return 1


def _demo():
    cases = [
        ("아무 문제 없는 글",
         "설포라판이 HDAC 활성을 억제한다는 근거가 있다 [PMC000001]. 병용 효과는 더 확인이 필요하다."),
        ("배합비가 섞였다",
         "본 조성물은 추출물 12.5중량% 배합, 배양물 3.0% 첨가로 제조하였다."),
        ("공정 조건이 섞였다",
         "1차 건조는 60도에서 90분, 2차 건조는 45도에서 120분 수행하였다."),
        ("출원 전 자료다",
         "[대외비] 본 자료는 출원 예정 기술을 포함한다. 문서번호 NPK-26-0413."),
        ("자격 증명이 섞였다",
         "설정에 api_key=sk-live-2f8a91c4d7 를 넣고 실행한다."),
    ]
    for level in ("internal", "restricted", "public"):
        print("=" * 62)
        print(f"등급: {level}")
        print("=" * 62)
        for title, text in cases:
            print(f"\n--- {title} ---")
            report(check(text, level), level)
    print()
    print("=" * 62)
    print("같은 글이 등급에 따라 다르게 걸린다. 공개용이 가장 엄격하다.")
    print("그리고 자격 증명은 어느 등급에서도 걸린다.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="검사할 파일")
    ap.add_argument("--level", default="restricted", choices=LEVELS)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.demo or not a.path:
        _demo()
        return 0
    text = Path(a.path).read_text(encoding="utf-8")
    return report(check(text, a.level), a.level)


if __name__ == "__main__":
    sys.exit(main())
