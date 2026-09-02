#!/usr/bin/env python3
"""
pdf_to_nxml.py — nxml 이 없으면 만든다 (14장 "없으면 만든다")

    python pdf_to_nxml.py paper.pdf --meta meta.json --out paper.nxml

두 단계다.
  1) convert_with_docling(pdf)  — 12장의 파싱 모델(Docling)로 레이아웃을 읽어
                                  {headings, paragraphs, figures, tables} 를 뽑는다
  2) assemble_nxml(meta, doc)   — 그것을 nxml 뼈대(<front>/<body>/<fig>/<table-wrap>)로 조립한다

서지(<front>)는 pdf 첫 장에서 긁지 않는다. 10장에서 받아 둔 NCBI 메타데이터(--meta)를 넣는다.
조립본은 <article source="pdf-built"> 로 출신을 표시해 둔다.

Docling 이 없는 환경에서도 2) 는 돈다 — 테스트와 학습용으로 분리해 두었다.
Qwen3-VL 로 캡션 짝짓기를 돕는 부분은 이 최소 예제에서 뺐다 (개념은 본문 참조).
"""
import argparse
import json
import sys
from pathlib import Path

from lxml import etree

# 윈도우 콘솔에서 한글·기호가 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- 1) Docling

def convert_with_docling(pdf: Path, image_dir: Path) -> dict:
    """pdf → {headings:[(level,text)], blocks:[(kind, payload)]}.
    blocks 는 읽는 순서대로: ("h", level, text) / ("p", text) / ("fig", caption, image_file) / ("tab", caption, rows)"""
    try:
        from docling.document_converter import DocumentConverter
        from docling_core.types.doc import DocItemLabel
    except ImportError as e:  # pragma: no cover
        raise SystemExit("docling 이 설치되어 있지 않다. pip install docling  (12장의 파싱 모델이 함께 내려온다)") from e

    result = DocumentConverter().convert(str(pdf))
    doc = result.document
    image_dir.mkdir(parents=True, exist_ok=True)

    blocks = []
    fig_n = tab_n = 0
    for item, level in doc.iterate_items():
        label = getattr(item, "label", None)
        if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
            blocks.append(("h", max(1, int(level)), item.text.strip()))
        elif label in (DocItemLabel.PARAGRAPH, DocItemLabel.TEXT):
            if item.text.strip():
                blocks.append(("p", item.text.strip()))
        elif label == DocItemLabel.PICTURE:
            fig_n += 1
            fname = f"fig{fig_n}.png"
            img = item.get_image(doc)
            if img is not None:
                img.save(image_dir / fname)
            caption = " ".join(c.text for c in getattr(item, "captions", []) if hasattr(c, "text")).strip()
            blocks.append(("fig", caption, fname))
        elif label == DocItemLabel.TABLE:
            tab_n += 1
            caption = " ".join(c.text for c in getattr(item, "captions", []) if hasattr(c, "text")).strip()
            rows = []
            try:
                df = item.export_to_dataframe()
                rows = [list(map(str, df.columns))] + [list(map(str, r)) for r in df.values.tolist()]
            except Exception:  # 병합 셀에서 자주 틀린다 — 캡션만이라도 건진다
                rows = []
            blocks.append(("tab", caption, rows))
    return {"blocks": blocks}


# ---------------------------------------------------------------- 2) 조립

def _sub(parent, tag, text=None, **attrs):
    el = etree.SubElement(parent, tag, **attrs)
    if text is not None:
        el.text = text
    return el


def assemble_nxml(meta: dict, doc: dict) -> etree._Element:
    """NCBI 서지 + Docling 블록 → nxml 뼈대. 뒷단 파서는 이것이 조립본인지 모른다."""
    XLINK = "http://www.w3.org/1999/xlink"
    article = etree.Element("article", nsmap={"xlink": XLINK}, source="pdf-built")

    # <front> — 서지는 추측하지 않는다. 받아 둔 메타데이터를 그대로.
    front = _sub(article, "front")
    jm = _sub(front, "journal-meta")
    _sub(_sub(jm, "journal-title-group"), "journal-title", meta.get("journal", ""))
    am = _sub(front, "article-meta")
    for key, typ in (("pmid", "pmid"), ("pmcid", "pmc"), ("doi", "doi")):
        if meta.get(key):
            _sub(am, "article-id", meta[key], **{"pub-id-type": typ})
    _sub(_sub(am, "title-group"), "article-title", meta.get("title", ""))
    if meta.get("year"):
        _sub(_sub(am, "pub-date"), "year", str(meta["year"]))

    # <body> — 제목 계층을 <sec> 중첩으로. 현재 열려 있는 섹션을 레벨별로 쌓아 둔다.
    body = _sub(article, "body")
    stack = [(0, body)]           # (level, element)
    fig_i = tab_i = 0
    for blk in doc["blocks"]:
        kind = blk[0]
        if kind == "h":
            level, text = blk[1], blk[2]
            while stack and stack[-1][0] >= level:
                stack.pop()
            sec = _sub(stack[-1][1], "sec")
            _sub(sec, "title", text)
            stack.append((level, sec))
            continue
        parent = stack[-1][1]
        if kind == "p":
            _sub(parent, "p", blk[1])
        elif kind == "fig":
            fig_i += 1
            fig = _sub(parent, "fig", id=f"F{fig_i}")
            _sub(fig, "label", f"Figure {fig_i}")
            _sub(_sub(fig, "caption"), "p", blk[1])
            _sub(fig, "graphic", **{f"{{{XLINK}}}href": blk[2]})
        elif kind == "tab":
            tab_i += 1
            tw = _sub(parent, "table-wrap", id=f"T{tab_i}")
            _sub(tw, "label", f"Table {tab_i}")
            _sub(_sub(tw, "caption"), "p", blk[1])
            table = _sub(tw, "table")
            for r_i, row in enumerate(blk[2]):
                tr = _sub(table, "tr")
                for cell in row:
                    _sub(tr, "th" if r_i == 0 else "td", cell)
    return article


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--meta", type=Path, required=True, help="NCBI 서지 json (title, doi, pmid, pmcid, journal, year)")
    ap.add_argument("--out", type=Path, required=True, help="조립할 .nxml 경로 (원본 nxml 과 같은 폴더·이름 규칙으로)")
    a = ap.parse_args()

    meta = json.loads(a.meta.read_text(encoding="utf-8"))
    doc = convert_with_docling(a.pdf, a.out.parent)
    article = assemble_nxml(meta, doc)
    a.out.write_bytes(etree.tostring(article, pretty_print=True, xml_declaration=True, encoding="UTF-8"))
    print(f"{a.pdf.name} → {a.out}  (블록 {len(doc['blocks'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
