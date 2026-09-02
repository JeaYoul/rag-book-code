#!/usr/bin/env python3
"""
scan_check.py — 이 pdf 는 글자인가, 사진인가 (14장 "끝내 넘지 못한 벽")

    python scan_check.py paper.pdf            # 종료코드 0 = 텍스트 있음, 3 = 스캔본
    python scan_check.py --dir papers/        # 폴더 전체를 훑어 표로 보여준다

판별은 단순하다. 텍스트 레이어에서 글자를 뽑아 봤을 때
페이지당 평균 글자 수가 기준(기본 20자) 아래면 스캔본으로 본다.
스캔본은 Docling 에 넣지 않고 격리 폴더로 보낸다.
"""
import argparse
import sys
from pathlib import Path

from pypdf import PdfReader

# 윈도우 콘솔에서 한글·기호가 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

THRESHOLD = 20  # 페이지당 글자 수. 이보다 적으면 '사진'


def chars_per_page(pdf: Path, max_pages: int = 5) -> float:
    reader = PdfReader(str(pdf))
    pages = reader.pages[:max_pages]
    if not pages:
        return 0.0
    total = sum(len((p.extract_text() or "").strip()) for p in pages)
    return total / len(pages)


def is_scanned(pdf: Path, threshold: float = THRESHOLD) -> bool:
    return chars_per_page(pdf) < threshold


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?", type=Path)
    ap.add_argument("--dir", type=Path)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    a = ap.parse_args()

    if a.dir:
        for pdf in sorted(a.dir.rglob("*.pdf")):
            cpp = chars_per_page(pdf)
            tag = "스캔본 → 격리" if cpp < a.threshold else "텍스트 있음"
            print(f"{cpp:8.1f} 자/쪽  {tag:12s}  {pdf}")
        return 0

    if not a.pdf:
        ap.error("pdf 파일 또는 --dir 을 주어라")
    cpp = chars_per_page(a.pdf)
    if cpp < a.threshold:
        print(f"{a.pdf.name}: 페이지당 {cpp:.1f}자 — 스캔본. 들이지 않는다.")
        return 3
    print(f"{a.pdf.name}: 페이지당 {cpp:.1f}자 — 텍스트 있음.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
