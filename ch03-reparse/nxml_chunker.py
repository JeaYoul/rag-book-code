"""
3장. 이미 끝낸 것을 스스로 태우다 — NXML 파싱과 캡션 엮기
《산골 농부의 RAG》 예제 코드

이 장의 핵심은 두 가지다.

  ① 추측하지 말고 구조를 믿어라
     PDF는 "여기가 제목인가?" 하고 짐작해야 한다. 짐작은 틀린다.
     .nxml 은 <title>, <fig>, <caption> 이 이미 태그로 명시돼 있다.
     → 진실이 이미 적혀 있으니, 추측할 필요가 없다.

  ② 그림의 의미를 잃지 마라
     논문의 알맹이는 그래프와 표 안에 있다. 글자만 긁으면 반쪽짜리다.
     그렇다고 AI에게 그림을 해석시키면 없는 숫자를 지어낸다(위험!).
     → 그림에 붙은 '캡션'을 본문 청크에 함께 엮는다. 안전하면서도 깊다.

[준비]
    표준 라이브러리만 쓴다. 설치할 것 없음.

[실행]
    python nxml_chunker.py
"""

import re
import xml.etree.ElementTree as ET


# ─────────────────────────────────────────────
# 샘플 논문 (.nxml 의 축소판)
# ─────────────────────────────────────────────
# 진짜 논문 nxml 은 수천 줄이지만, 구조는 정확히 이렇게 생겼다.
# 눈여겨볼 것: 무엇이 제목이고 무엇이 그림인지 '태그로 명시'돼 있다는 점.
SAMPLE_NXML = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group>
        <article-title>설포라판의 HDAC 억제 효과에 관한 연구</article-title>
      </title-group>
      <article-id pub-id-type="pmc">PMC1234567</article-id>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>브로콜리새싹에는 설포라판의 전구체인 글루코라파닌이 풍부하다.
         설포라판은 Nrf2 경로를 활성화하는 것으로 알려져 있다.</p>
    </sec>
    <sec>
      <title>Results</title>
      <p>설포라판 처리군에서 HDAC 활성의 유의한 감소가 관찰되었다.
         이 효과는 농도 의존적이었다.</p>
      <fig id="fig1">
        <label>Figure 1</label>
        <caption>
          <p>설포라판 농도(10, 25, 50 µM)에 따른 HDAC 억제율 변화. 
             50 µM에서 최대 68% 억제를 보였다.</p>
        </caption>
        <graphic xlink:href="fig1.jpg"/>
      </fig>
      <p>부티르산 병용 시 시너지 효과가 확인되었다.</p>
      <table-wrap id="tbl1">
        <label>Table 1</label>
        <caption>
          <p>설포라판과 부티르산 병용 처리의 조합지수(CI) 분석 결과.</p>
        </caption>
      </table-wrap>
    </sec>
  </body>
</article>
"""


# ─────────────────────────────────────────────
# ① 구조를 그대로 읽어낸다 (추측이 아니라)
# ─────────────────────────────────────────────
# PDF였다면 "이 글씨가 크니까 제목인가?" 하고 짐작해야 한다.
# nxml 은 <article-title> 이라고 적혀 있다. 그냥 읽으면 된다.
def parse_nxml(xml_text):
    """nxml 에서 제목·본문·그림·표를 구조 그대로 뽑아낸다"""
    root = ET.fromstring(xml_text)

    # 제목 — 태그에 명시돼 있으니 추측할 필요가 없다
    title_el = root.find(".//article-title")
    title = title_el.text.strip() if title_el is not None else ""

    # 그림 — <fig> 안의 <caption> 을 그대로 가져온다.
    #        어느 캡션이 어느 그림 것인지 헷갈릴 일이 없다. 구조가 말해주니까.
    figures = []
    for fig in root.iter("fig"):
        label = fig.findtext("label", default="").strip()
        caption = " ".join(fig.find("caption").itertext()).strip() \
                  if fig.find("caption") is not None else ""
        figures.append({
            "id": fig.get("id"),
            "label": label,
            "caption": _clean(caption),
        })

    # 표 — <table-wrap> 도 똑같은 방식
    tables = []
    for tbl in root.iter("table-wrap"):
        label = tbl.findtext("label", default="").strip()
        caption = " ".join(tbl.find("caption").itertext()).strip() \
                  if tbl.find("caption") is not None else ""
        tables.append({
            "id": tbl.get("id"),
            "label": label,
            "caption": _clean(caption),
        })

    # 본문 — 섹션(<sec>)별로 문단(<p>)을 모은다
    sections = []
    for sec in root.iter("sec"):
        sec_title = sec.findtext("title", default="").strip()
        paragraphs = [_clean(" ".join(p.itertext())) for p in sec.findall("p")]
        sections.append({
            "title": sec_title,
            "text": " ".join(paragraphs),
        })

    return {"title": title, "sections": sections,
            "figures": figures, "tables": tables}


def _clean(text):
    """줄바꿈과 여러 공백을 하나로 정리"""
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────
# ② 캡션을 본문 청크에 엮어 넣는다  ← 이 장의 심장
# ─────────────────────────────────────────────
# 여기가 3장에서 가장 중요한 부분이다.
#
# 그림을 AI에게 '해석'시키지 않는다. 없는 숫자를 지어낼 위험이 있으니까.
# 대신 그림에 붙은 '캡션'을 본문 조각에 딸려 붙인다.
# → 검색이 그림의 '의미'에는 닿되, 숫자를 날조하지는 않는다. 안전하다.
def build_chunks(paper, attach_captions=True):
    """섹션을 청크로 만들되, 관련 그림·표 캡션을 함께 엮는다"""
    chunks = []

    for sec in paper["sections"]:
        content = sec["text"]

        # ★ 핵심: 이 섹션에 딸린 그림·표의 캡션을 청크 뒤에 붙인다
        if attach_captions and sec["title"].lower() == "results":
            for fig in paper["figures"]:
                content += f"\n[{fig['label']}] {fig['caption']}"
            for tbl in paper["tables"]:
                content += f"\n[{tbl['label']}] {tbl['caption']}"

        chunks.append({
            "paper_title": paper["title"],
            "section": sec["title"],
            "content": content,
        })

    return chunks


# ─────────────────────────────────────────────
# 실행 — 전과 후를 눈으로 비교해 보자
# ─────────────────────────────────────────────
if __name__ == "__main__":
    paper = parse_nxml(SAMPLE_NXML)

    print("=" * 60)
    print("① 구조를 그대로 읽어냈다 (추측 없이)")
    print("=" * 60)
    print(f"제목: {paper['title']}")
    print(f"섹션: {len(paper['sections'])}개")
    print(f"그림: {len(paper['figures'])}개, 표: {len(paper['tables'])}개")
    for fig in paper["figures"]:
        print(f"   └ {fig['label']}: {fig['caption'][:40]}...")

    print()
    print("=" * 60)
    print("② 캡션을 엮기 [전] — 글자만 긁은 반쪽짜리")
    print("=" * 60)
    before = build_chunks(paper, attach_captions=False)
    for c in before:
        if c["section"] == "Results":
            print(c["content"])

    print()
    print("=" * 60)
    print("② 캡션을 엮은 [후] — 그림의 의미까지 품은 청크")
    print("=" * 60)
    after = build_chunks(paper, attach_captions=True)
    for c in after:
        if c["section"] == "Results":
            print(c["content"])

    print()
    print("-" * 60)
    print("차이를 보라.")
    print("[전] 청크로는 '농도별 억제율'을 물어도 답할 수 없다.")
    print("[후] 청크는 '50µM에서 68% 억제'라는 근거를 품고 있다.")
    print("     — 그런데 AI가 그림을 해석해서 지어낸 게 아니라,")
    print("        원저자가 직접 쓴 캡션이다. 안전하면서도 깊다.")
