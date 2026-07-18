#!/usr/bin/env python3
"""
02_select.py — 목록을 보고 '받을 대상'만 골라낸다 (10장 ②)

십만 편을 다 받지 않는다. 무엇을 넣을지만큼 '무엇을 넣지 않을지'가 중요하다(3장).
선별은 데이터베이스의 순도를 지키는 첫 관문이다.

여기서는 기계적으로 거를 수 있는 것만 처리한다:
  - 발행 연도 결손/범위 밖
  - 중복(제목 기준)
  - 메타데이터 결손(제목·저자 비어있음)
실제 '분야 적합성' 판단은 사람이 목록을 훑으며 하는 게 가장 정확하다.
(원한다면 selected 컬럼을 손으로 편집하는 방식도 좋다.)

⚠️ 템플릿입니다. 선별 기준(<...>)을 자기 상황에 맞게 조정하세요.

사용:
  python 02_select.py --in lists/<분야>.csv --out lists/<분야>_selected.csv
"""

import csv
import argparse


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select(rows: list[dict], min_year: int | None) -> list[dict]:
    seen_titles = set()
    kept = []
    dropped = {"결손": 0, "중복": 0, "연도": 0}

    for r in rows:
        title = (r.get("title") or "").strip().lower()
        authors = (r.get("authors") or "").strip()
        year_raw = (r.get("year") or "").strip()[:4]

        # 1) 메타데이터 결손
        if not title or not authors:
            dropped["결손"] += 1
            continue

        # 2) 중복 (제목 기준)
        if title in seen_titles:
            dropped["중복"] += 1
            continue

        # 3) 연도 필터 (선택)
        if min_year is not None:
            try:
                if int(year_raw) < min_year:
                    dropped["연도"] += 1
                    continue
            except ValueError:
                # 연도 파싱 불가 → 일단 보류하지 않고 통과시킬지 결정
                pass

        seen_titles.add(title)
        kept.append(r)

    print(f"선별: {len(kept)}편 통과 / 제외 {dropped}")
    return kept


def save(rows: list[dict], path: str) -> None:
    if not rows:
        print("통과한 논문이 없습니다.")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"선별 목록 저장: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-year", type=int, default=None,
                    help="<선택> 이 연도 미만 제외. 예: 2015")
    args = ap.parse_args()

    rows = load(args.inp)
    kept = select(rows, args.min_year)
    save(kept, args.out)
    print("→ 이제 03_download.py 로 본문을 받으세요.")


if __name__ == "__main__":
    main()
