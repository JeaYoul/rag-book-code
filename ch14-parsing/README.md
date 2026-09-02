# 14장. 문서를 조각으로 — 파싱 파이프라인

논문 한 편이 갈림길을 지나 **패키지** 하나가 되기까지. 그리고 그 일을 구만 편에 걸쳐, 죽어도 이어가며 돌리는 법.

```
/papers/<ID>/ ─┬─ *.nxml 있음 ──────────────────────────┐
               └─ *.pdf 만 ─ scan_check ─ 스캔본? ─ 격리    │
                                └─ pdf_to_nxml (Docling) ──┤ 합류
                                                            ▼
                                              nxml_parser ─→ /packages/<ID>/  + parsing_checkpoint.json
```

## 파일

| 파일 | 역할 |
|---|---|
| `nxml_parser.py` | nxml 한 편 → 패키지. front 신원 대조 · sec 나무 따라 문단 · fig/table-wrap · 참고문헌은 읽지 않음 |
| `pdf_to_nxml.py` | pdf → Docling 레이아웃 → NCBI 서지와 결합해 nxml 조립 (출신 `source="pdf-built"` 표시) |
| `scan_check.py` | 텍스트 레이어가 있는가. 페이지당 글자 수로 스캔본을 가려 격리 |
| `phoenix_loop.py` | JSON 체크포인트(`processed`/`failed`/`last_index`)로 이어가는 루프. 반쪽 결과는 비우고 다시 |
| `run_parser.sh` | 불사조. 셸 `while true` 안에서 `docker run --rm` 으로 매번 새 컨테이너 — 실제 `auto_parse.sh` 의 뼈대 |
| `Dockerfile` | 파서 컨테이너 이미지 |
| `sample/` | 실습용 가짜 논문 셋(정상 둘, 신원 어긋난 것 하나)과 목록 csv. 그림 파일은 자리만 채운 빈 껍데기다 |

## 해보기

**1. nxml 한 편을 뜯어 본다.**

```bash
pip install -r requirements.txt
python nxml_parser.py sample/PMC000001/PMC000001.nxml --out /tmp/pkg/PMC000001 --list sample/list.csv
cat /tmp/pkg/PMC000001/sections.json    # 섹션 경로가 붙은 문단들
cat /tmp/pkg/PMC000001/figures.json     # <fig> 안의 <caption> — 짝이 확실하다
```

**2. 불사조를 돌려 본다. 일부러 죽여 본다.**

```bash
python phoenix_loop.py --papers sample --packages /tmp/pkg --list sample/list.csv --crash-after 1
#   → 첫 논문을 저장하고, 체크포인트에 올리기 전에 쓰러진다
cat /tmp/pkg/parsing_checkpoint.json
#   → processed 는 비어 있다. 죽다 만 논문의 폴더만 남아 있다
python phoenix_loop.py --papers sample --packages /tmp/pkg --list sample/list.csv
#   → 새 배가 뜬다. 반쪽을 비우고 다시 하고, 끝까지 간다
```

도커로 하려면 `run_parser.sh`. `while` 루프가 30초마다 새 컨테이너를 띄우는 것을 로그로 지켜보라.

**3. pdf 가 사진인지 글자인지.**

```bash
python scan_check.py --dir papers/
```

## 정직하게

- 이 코드는 **가르치기 위한 최소 예제**다. 실제 파서는 예외 처리가 이보다 훨씬 길다(제목 없는 섹션, 수식, 표 안 줄바꿈, 캡션 없는 그림 …). 뼈대만 남겼다.
- 실제 시스템에서는 참고문헌 조각을 아예 버리지 않고 `is_reference_section` 표시를 달아 검색에서 거른다. 이 예제는 단순하게 `<back>` 을 읽지 않는다.
- `pdf_to_nxml.py` 의 Docling 부분은 이 저장소에서 자동 테스트하지 않았다. Docling 버전에 따라 항목 이름이 다를 수 있다. 조립 함수(`assemble_nxml`)는 Docling 없이도 돌고, 테스트했다.
- 실제 첫 파싱에서는 Docling 을 GPU 가 아니라 CPU 로 돌렸다 (`DOCLING_DEVICE=cpu`). 느리지만 죽지 않는 쪽을 골랐다.
- Qwen3-VL 로 캡션을 짝짓는 보조 단계는 뺐다. 원리는 책 본문에.
