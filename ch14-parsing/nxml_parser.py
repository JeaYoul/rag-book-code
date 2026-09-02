#!/usr/bin/env python3
"""
nxml_parser.py — JATS(.nxml) 논문 한 편을 "패키지" 하나로 뜯는다 (14장)

    python nxml_parser.py paper.nxml --out packages/PMC123456 [--list lists/verified.csv]

패키지 안에 남기는 것:
    meta.json      서지 (front)
    sections.json  섹션 경로가 붙은 문단들 (body)      → 15장에서 청킹
    figures.json   그림 라벨·캡션·이미지 파일명·섹션 경로 → 캡션 "연결"까지 (엮기는 15장)
    tables.json    표 라벨·캡션·행 단위로 펼친 본문
    images/        그림 파일 복사본                     → MongoDB로

버리는 것:
    back (참고문헌) — 검색을 오염시키는 잡음

--list 를 주면 front 의 신원(PMCID/PMID/DOI/제목)을 10장 목록과 대조하고,
어긋나면 IdentityMismatch 를 던진다 (호출한 쪽이 격리 폴더로 보낸다).
"""
import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

from lxml import etree

# 윈도우 콘솔에서 한글·기호가 깨지지 않게
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


class IdentityMismatch(Exception):
    """front 에 적힌 신원이 목록과 다르다."""


# ---------------------------------------------------------------- 공통

def text_of(el) -> str:
    """태그를 걷어내고 글자만, 공백은 하나로."""
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def section_path_of(el) -> str:
    """이 요소가 어느 섹션 아래 있는지. 'Results > Cell viability' 꼴."""
    titles = []
    for sec in el.iterancestors("sec"):
        t = text_of(sec.find("title"))
        if t:
            titles.append(t)
    return " > ".join(reversed(titles))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", (s or "").lower())


# ---------------------------------------------------------------- ① front

def read_front(root) -> dict:
    am = root.find("front/article-meta")
    jm = root.find("front/journal-meta")
    ids = {}
    if am is not None:
        for aid in am.findall("article-id"):
            ids[aid.get("pub-id-type", "")] = text_of(aid)
    year = ""
    if am is not None:
        for pd in am.findall("pub-date"):
            y = text_of(pd.find("year"))
            if y:
                year = y
                break
    return {
        "title": text_of(am.find("title-group/article-title")) if am is not None else "",
        "doi": ids.get("doi", ""),
        "pmid": ids.get("pmid", ""),
        "pmcid": ids.get("pmc", "") or ids.get("pmcid", ""),
        "journal": text_of(jm.find(".//journal-title")) if jm is not None else "",
        "year": year,
    }


def verify_identity(meta: dict, list_csv: Path) -> None:
    """10장 목록(csv)과 대조. pmcid 또는 pmid 로 행을 찾고, doi·제목을 맞춰 본다."""
    with open(list_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    row = next((r for r in rows
                if (meta["pmcid"] and r.get("pmcid", "").strip() == meta["pmcid"])
                or (meta["pmid"] and r.get("pmid", "").strip() == meta["pmid"])), None)
    if row is None:
        raise IdentityMismatch(f"목록에 없는 논문: pmcid={meta['pmcid']} pmid={meta['pmid']}")

    score, checks = 0, []
    if meta["doi"] and row.get("doi"):
        ok = meta["doi"].lower() == row["doi"].strip().lower()
        score += 2 if ok else 0
        checks.append(("doi", ok))
    if meta["title"] and row.get("title"):
        ok = norm(meta["title"]) == norm(row["title"])
        score += 1 if ok else 0
        checks.append(("title", ok))
    if any(not ok for _, ok in checks):
        bad = ", ".join(k for k, ok in checks if not ok)
        raise IdentityMismatch(f"신원 불일치({bad}): 파일={meta['title'][:40]!r} 목록={row.get('title','')[:40]!r}")


# ---------------------------------------------------------------- ② body

def para_text(p) -> str:
    """문단 글자. 인용 번호(<xref ref-type="bibr">)는 검색 잡음이라 걷어낸다."""
    parts = []
    for node in p.iter():
        if node.tag == "xref" and node.get("ref-type") == "bibr":
            if node.tail:
                parts.append(node.tail)
            continue
        if node.text and not (node.getparent() is not None and node.getparent().tag == "xref"
                              and node.getparent().get("ref-type") == "bibr"):
            parts.append(node.text)
        if node is not p and node.tail and node.tag != "xref":
            parts.append(node.tail)
    return " ".join("".join(parts).split())


def walk(sec, path):
    """<sec> 나무를 따라 (섹션 경로, 문단) 을 낸다. 자기 자신을 다시 부른다."""
    title = text_of(sec.find("title"))
    here = path + [title] if title else path
    for p in sec.findall("p"):
        t = para_text(p)
        if t:
            yield " > ".join(here), t
    for sub in sec.findall("sec"):
        yield from walk(sub, here)


def read_body(root) -> list:
    body = root.find("body")
    out = []
    if body is None:
        return out
    for p in body.findall("p"):                      # 섹션 없이 본문에 바로 놓인 문단
        t = para_text(p)
        if t:
            out.append({"section": "", "text": t})
    for sec in body.findall("sec"):
        for section, text in walk(sec, []):
            out.append({"section": section, "text": text})
    return out


# ---------------------------------------------------------------- ③ fig / table-wrap

def collect_figures(root) -> list:
    """<fig> 전부 — 본문 안이든 <floats-group> 안이든. 캡션은 <fig> 안에 있으니 짝이 확실하다."""
    figs = []
    for fig in root.iter("fig"):
        g = fig.find(".//graphic")
        figs.append({
            "id": fig.get("id", ""),
            "label": text_of(fig.find("label")),
            "caption": text_of(fig.find("caption")),
            "graphic": g.get(XLINK_HREF, "") if g is not None else "",
            "section": section_path_of(fig),
        })
    return figs


def collect_tables(root) -> list:
    tables = []
    for tw in root.iter("table-wrap"):
        rows = []
        for tr in tw.iter("tr"):
            cells = [text_of(c) for c in tr if c.tag in ("td", "th")]
            if any(cells):
                rows.append(" | ".join(cells))
        tables.append({
            "id": tw.get("id", ""),
            "label": text_of(tw.find("label")),
            "caption": text_of(tw.find("caption")),
            "rows": rows,
            "section": section_path_of(tw),
        })
    return tables


# ---------------------------------------------------------------- 패키지

def copy_graphics(figures: list, src_dir: Path, img_dir: Path) -> int:
    """graphic 파일을 images/ 로. 확장자가 빠진 href 도 흔하니 몇 가지를 시도한다."""
    img_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for fig in figures:
        href = fig["graphic"]
        if not href:
            continue
        cands = [src_dir / href] + [src_dir / f"{href}{ext}" for ext in (".jpg", ".jpeg", ".png", ".tif", ".gif")]
        src = next((c for c in cands if c.exists()), None)
        if src is not None:
            shutil.copy2(src, img_dir / src.name)
            fig["image_file"] = src.name
            n += 1
    return n


def parse_one(nxml_path: Path, out_dir: Path, list_csv: Path | None = None) -> dict:
    root = etree.parse(str(nxml_path)).getroot()

    meta = read_front(root)                       # ① 신원
    if list_csv is not None:
        verify_identity(meta, list_csv)           #    믿되, 확인하라
    sections = read_body(root)                    # ② 문단 (섹션 경로 포함)
    figures = collect_figures(root)               # ③ 그림
    tables = collect_tables(root)                 #    표
    #                                              ④ back 은 읽지 않는다

    out_dir.mkdir(parents=True, exist_ok=True)
    copy_graphics(figures, nxml_path.parent, out_dir / "images")
    for name, obj in (("meta", meta), ("sections", sections), ("figures", figures), ("tables", tables)):
        (out_dir / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"paragraphs": len(sections), "figures": len(figures), "tables": len(tables)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nxml", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--list", type=Path, default=None, help="10장에서 확정한 목록 csv (pmcid,pmid,doi,title)")
    a = ap.parse_args()
    try:
        r = parse_one(a.nxml, a.out, a.list)
    except IdentityMismatch as e:
        print(f"[격리] {a.nxml.name}: {e}", file=sys.stderr)
        return 2
    print(f"{a.nxml.name}: 문단 {r['paragraphs']} · 그림 {r['figures']} · 표 {r['tables']} → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
