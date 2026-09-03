#!/usr/bin/env python3
"""
patent_chunker.py — 청구항은 자르지 않는다 (23장)

    python patent_chunker.py sample/patent_sample.txt
    python patent_chunker.py sample/patent_sample.txt --max-chars 400

15장에서 논문을 800자쯤으로 나누며 "문장 중간에서 자르지 말라"고 했다.
특허에서는 그 원칙이 더 강해진다.

청구항은 읽는 글이 아니라 **경계를 그리는 글**이다.
한 문장이 반 페이지가 되고, 그 문장의 낱말 하나가 권리 범위를 바꾼다.
반으로 자른 청구항은 뜻이 반이 되는 것이 아니라 **아예 다른 뜻**이 된다.

그래서 이 조각기의 규칙은 하나다.
    청구항은 길이가 얼마든 통째로 한 조각.  (is_atomic = True)
    명세서 본문은 15장과 같은 방식으로 나눈다.

한 가지 더. 이것을 만들며 알게 된 것인데, **청구항은 대개 한 문장이다.**
그래서 15장의 "문장 경계를 지켜 자른다" 규칙만으로는 애초에 자를 수 없다.
위험한 것은 문자 수만 세어 자르는 조각기다. --compare 로 그것을 보여 준다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

# 청구항 시작을 알아보는 표시들. 나라와 서식마다 다르니 넉넉히 잡는다
CLAIM_HEAD = re.compile(r"^\s*(?:\[?청구항\s*(\d+)\]?|청구범위|What is claimed|Claims?)\s*[:.]?\s*", re.M)
CLAIM_NUM = re.compile(r"^\s*(?:\[?청구항\s*(\d+)\]?|(\d+)\s*[.)])\s*")
SECTION_HEAD = re.compile(r"^\s*(?:\[?(발명의 명칭|기술분야|배경기술|해결하려는 과제|과제의 해결 수단|"
                          r"발명의 효과|도면의 간단한 설명|발명을 실시하기 위한 구체적인 내용|"
                          r"산업상 이용가능성|요약|초록)\]?)\s*$", re.M)


def split_sections(text):
    """[제목] 형태의 절 표시로 문서를 나눈다. 표시가 없으면 통째로 하나."""
    marks = [(m.start(), m.group(1)) for m in SECTION_HEAD.finditer(text)]
    if not marks:
        return [("본문", text)]
    out = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end]
        body = SECTION_HEAD.sub("", body, count=1).strip()
        if body:
            out.append((name, body))
    if marks[0][0] > 0 and text[:marks[0][0]].strip():
        out.insert(0, ("머리", text[:marks[0][0]].strip()))
    return out


def split_claims(text):
    """청구항 영역을 청구항 단위로 나눈다. 각각이 한 조각이 된다."""
    lines = text.splitlines()
    claims, cur = [], []
    for ln in lines:
        if CLAIM_NUM.match(ln) and cur:
            claims.append("\n".join(cur).strip())
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        claims.append("\n".join(cur).strip())
    return [c for c in claims if c]


def split_text(body, max_chars=800, overlap=100):
    """15장의 방식. 문장 경계를 지키며 자른다."""
    if len(body) <= max_chars:
        return [body]
    sents = re.split(r"(?<=[.。?!])\s+|\n\n+", body)
    out, cur = [], ""
    for sent in sents:
        if not sent.strip():
            continue
        if len(cur) + len(sent) + 1 <= max_chars:
            cur = (cur + " " + sent).strip()
        else:
            if cur:
                out.append(cur)
            cur = (cur[-overlap:] + " " + sent).strip() if overlap and cur else sent
    if cur:
        out.append(cur)
    return out


def chunk_patent(text, max_chars=800, overlap=100):
    """특허 한 편 → 조각 목록. 청구항은 통째로, 본문은 나눠서."""
    chunks = []
    head = CLAIM_HEAD.search(text)
    if head:
        spec_part, claim_part = text[:head.start()], text[head.start():]
        claim_part = CLAIM_HEAD.sub("", claim_part, count=1)
    else:
        spec_part, claim_part = text, ""

    # 명세서 — 15장과 같이
    for name, body in split_sections(spec_part):
        for piece in split_text(body, max_chars, overlap):
            chunks.append({"chunk_type": "text", "is_atomic": False, "section": name, "content": piece})

    # 청구항 — 길이에 상관없이 통째로
    for i, claim in enumerate(split_claims(claim_part), 1):
        m = CLAIM_NUM.match(claim)
        num = (m.group(1) or m.group(2)) if m else str(i)
        body = CLAIM_NUM.sub("", claim, count=1).strip()      # 머리는 떼고 section 으로 옮긴다
        chunks.append({"chunk_type": "claim", "is_atomic": True,
                       "section": f"청구항 {num}", "content": body})

    return chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--max-chars", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=100)
    ap.add_argument("--out", help="JSONL 로 저장")
    ap.add_argument("--compare", action="store_true", help="문자 수로만 자르면 어떻게 되는지 보여 준다")
    a = ap.parse_args()

    text = Path(a.path).read_text(encoding="utf-8")
    chunks = chunk_patent(text, a.max_chars, a.overlap)

    claims = [c for c in chunks if c["chunk_type"] == "claim"]
    texts = [c for c in chunks if c["chunk_type"] == "text"]
    print(f"조각 {len(chunks)}개  (명세서 {len(texts)} · 청구항 {len(claims)})")
    print(f"상한 {a.max_chars}자")
    print()
    for c in chunks:
        mark = "[통째]" if c["is_atomic"] else "      "
        over = " ← 상한을 넘지만 자르지 않았다" if c["is_atomic"] and len(c["content"]) > a.max_chars else ""
        print(f"{mark} {c['section']:<12} {len(c['content']):>5}자  {c['content'][:44].replace(chr(10),' ')}…{over}")

    long_claims = [c for c in claims if len(c["content"]) > a.max_chars]
    print()
    if long_claims:
        print(f"상한을 넘는 청구항 {len(long_claims)}개 — 자르지 않고 통째로 두었다.")
        print("반으로 자른 청구항은 뜻이 반이 되는 것이 아니라 아예 다른 뜻이 된다.")
    bad = [c for c in claims if not c["is_atomic"]]
    print("청구항 중 잘린 것:", len(bad), "(0이어야 한다)")

    if a.compare and long_claims:
        _compare(long_claims[0], a.max_chars)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print("저장:", a.out)
    return 0


def _compare(claim, max_chars):
    """문자 수만 세어 자르면 무엇이 사라지는지."""
    body = claim["content"]
    print()
    print("=" * 62)
    print(f"문자 수로만 자르면 ({claim['section']}, {len(body)}자 → 상한 {max_chars}자)")
    print("=" * 62)
    pieces = [body[i:i + max_chars] for i in range(0, len(body), max_chars)]
    for i, piece in enumerate(pieces, 1):
        print()
        print(f"[조각 {i}] {len(piece)}자")
        print("  " + piece[:120].replace("\n", " ") + ("…" if len(piece) > 120 else ""))
    print()
    print(f"조각 {len(pieces)}개로 쪼개졌다. 조각 1만 검색에 걸리면 이렇게 읽힌다:")
    print("  '두 층의 접촉 면적을 제한한 조성물'")
    print()
    print("뒤 조각에 있던 수분 함량, 입도, 포장재, 유지율 조건이 사라졌다.")
    print("권리 범위가 넓어진 것이 아니라 다른 발명이 되었다.")
    print("논문이라면 조각 하나가 부실해도 다른 조각이 메운다. 청구항은 메울 수 없다.")
    print("그래서 자르지 않는다.")


if __name__ == "__main__":
    sys.exit(main())
