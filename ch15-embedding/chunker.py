#!/usr/bin/env python3
"""
chunker.py — 14장 패키지 하나를 조각(청크)으로 (15장 "청킹 실행")

    python chunker.py packages/PMC000001 --out chunks/PMC000001.jsonl

세 종류의 조각을 만든다 (실제 DB 의 chunk_type 과 같다):
    text            본문 — 섹션이 단위. 긴 섹션은 simple_chunker 로 나눈다
    figure_caption  그림 캡션 하나 = 조각 하나 (figure_id 로 그림 행 → MongoDB 실물)
    table_data      표 하나 = 조각 하나 (캡션 + 행 텍스트, 원래 구조는 table_data JSON)

각 조각에는:
    context_header        "논문 제목 | 섹션 경로" 한 줄 — 벡터로 바꿀 글(content) 앞에 붙는다
    content               임베딩용 글 (머리글 + 본문)
    content_for_llm       LLM 에 근거로 건넬 글 (머리글 없는 본문)
    is_reference_section  참고문헌에서 나온 조각인가 — 검색에서 거른다

첫 파싱(2장) 규칙은 simple_chunker(500자, 100자 겹침). 재파싱에서는 --chunk-size 를 키웠다.
"""
import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

REFERENCE_WORDS = ("reference", "bibliography", "literature cited")


# ---------------------------------------------------------------- 첫 파싱의 열 줄 (2장)

def simple_chunker(sections, chunk_size=500, overlap=100):
    """섹션 기반 청킹. 긴 섹션은 chunk_size 로 나누되 문장 끝('. ')에서 자르려 하고, overlap 만큼 겹친다."""
    chunks = []
    for sec in sections:
        content, name = sec["content"], sec["name"]
        if len(content) <= chunk_size:
            if content.strip():
                chunks.append({"section": name, "content": content.strip()})
            continue
        start = 0
        while start < len(content):
            end = start + chunk_size
            piece = content[start:end]
            if end < len(content):                          # 문장 경계에서 자르기 시도
                last_period = piece.rfind(". ")
                if last_period > chunk_size * 0.5:
                    piece = piece[:last_period + 1]
                    end = start + last_period + 1
            if piece.strip():
                chunks.append({"section": name, "content": piece.strip()})
            start = end - overlap if end < len(content) else end
    return chunks


# ---------------------------------------------------------------- 재파싱의 규칙 (3장·15장)

def group_by_section(paragraphs):
    """14장 sections.json (섹션 경로가 붙은 문단들) → [{name, content}] — 같은 경로의 문단을 잇는다."""
    out, cur_name, buf = [], None, []
    for p in paragraphs:
        if p["section"] != cur_name:
            if buf:
                out.append({"name": cur_name or "", "content": "\n\n".join(buf)})
            cur_name, buf = p["section"], []
        buf.append(p["text"])
    if buf:
        out.append({"name": cur_name or "", "content": "\n\n".join(buf)})
    return out


def is_reference(section_name: str) -> bool:
    s = (section_name or "").lower()
    return any(w in s for w in REFERENCE_WORDS)


def make_chunks(package_dir: Path, chunk_size=1100, overlap=100):
    """패키지 하나 → 조각 목록. 본문·그림 캡션·표를 각각 제 조각으로."""
    meta = json.loads((package_dir / "meta.json").read_text(encoding="utf-8"))
    paragraphs = json.loads((package_dir / "sections.json").read_text(encoding="utf-8"))
    figures = json.loads((package_dir / "figures.json").read_text(encoding="utf-8"))
    tables = json.loads((package_dir / "tables.json").read_text(encoding="utf-8"))
    paper_id = meta.get("pmcid") or package_dir.name
    title = meta.get("title", "")

    def header(section):                      # 조각의 머리글 — 논문 제목 | 섹션 경로
        return f"{title} | {section}" if section else title

    chunks = []

    # ① 본문 — 섹션이 단위, 긴 섹션은 나눈다
    for i, c in enumerate(simple_chunker(group_by_section(paragraphs), chunk_size, overlap)):
        h = header(c["section"])
        chunks.append({
            "chunk_id": f"{paper_id}_text_{i:04d}",
            "paper_id": paper_id,
            "chunk_type": "text",
            "section": c["section"],
            "context_header": h,
            "content": f"{h}\n{c['content']}",           # 임베딩용 — 머리글 포함
            "content_for_llm": c["content"],             # LLM 용 — 본문만
            "char_count": len(c["content"]),
            "is_reference_section": is_reference(c["section"]),
            "figure_id": None, "table_id": None, "table_data": None,
        })

    # ② 그림 캡션 — 캡션 하나 = 조각 하나
    for i, f in enumerate(figures):
        if not f.get("caption"):
            continue
        h = header(f.get("section", ""))
        body = f"{f.get('label', '')}. {f['caption']}".strip(". ")
        chunks.append({
            "chunk_id": f"{paper_id}_fig_{i:04d}",
            "paper_id": paper_id,
            "chunk_type": "figure_caption",
            "section": f.get("section", ""),
            "context_header": h,
            "content": f"{h}\n{body}",
            "content_for_llm": body,
            "char_count": len(body),
            "is_reference_section": False,
            "figure_id": f"{paper_id}_{f.get('id') or i}", "table_id": None, "table_data": None,
        })

    # ③ 표 — 표 하나 = 조각 하나 (캡션 + 행 텍스트 / 구조는 JSON 으로)
    for i, t in enumerate(tables):
        h = header(t.get("section", ""))
        body = "\n".join([f"{t.get('label', '')}. {t.get('caption', '')}".strip(". ")] + t.get("rows", []))
        chunks.append({
            "chunk_id": f"{paper_id}_tab_{i:04d}",
            "paper_id": paper_id,
            "chunk_type": "table_data",
            "section": t.get("section", ""),
            "context_header": h,
            "content": f"{h}\n{body}",
            "content_for_llm": body,
            "char_count": len(body),
            "is_reference_section": False,
            "figure_id": None, "table_id": f"{paper_id}_{t.get('id') or i}",
            "table_data": {"label": t.get("label"), "caption": t.get("caption"), "rows": t.get("rows", [])},
        })
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", type=Path, help="14장 패키지 폴더 (meta/sections/figures/tables.json)")
    ap.add_argument("--out", type=Path, required=True, help="조각을 한 줄에 하나씩 쓸 jsonl")
    ap.add_argument("--chunk-size", type=int, default=1100, help="본문 조각 크기(글자). 첫 파싱은 500")
    ap.add_argument("--overlap", type=int, default=100)
    a = ap.parse_args()

    chunks = make_chunks(a.package, a.chunk_size, a.overlap)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    kinds = {}
    for c in chunks:
        kinds[c["chunk_type"]] = kinds.get(c["chunk_type"], 0) + 1
    print(f"{a.package.name}: 조각 {len(chunks)}개 {kinds} → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
