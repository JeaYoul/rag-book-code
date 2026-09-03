# 18장. 연구자의 손에 쥐여주다 — 애플리케이션

터미널 안의 시스템을 화면으로. 로그인 → 검색 → 답 → 보고서로 남기고 → 용어가 쌓이고 → 문서로 뽑는다.

```
Home.py (로그인 · 대시보드) ─ pages/1_논문_검색.py ─┬─ reports.py   보고서 저장 · 내 보고서
        auth.py (역할 셋 · bcrypt · 5회 잠금)         ├─ glossary.py  용어사전 (꺼내 쓰기 · 등록 · 검토)
        db.py  (PostgreSQL 또는 SQLite)               └─ exporter.py  중간 형식 → HTML · Word · PDF · PPT
        pages/9_용어_관리.py · pages/11_감사_로그.py
```

## 파일

| 파일 | 역할 |
|---|---|
| `db.py` | `PG_DSN` 이 있으면 PostgreSQL, 없으면 `app.sqlite`. 테이블 여섯 개 스키마 |
| `auth.py` | 역할 셋(researcher/core/admin)과 권한, bcrypt 해시, 다섯 번 실패 잠금, 로그인 시도·관리자 행위 기록 |
| `Home.py` | 로그인 폼(세션 120분), 대시보드, 비밀번호 바꾸기, 관리자의 사용자 만들기. `require_login()` 이 모든 화면의 문 |
| `pages/1_논문_검색.py` | 슬라이더·모드·질문 폼 → 16장 검색 → 답 + 참고문헌 → 용어 해설 → 저장 버튼 → 문서 4종 |
| `pages/9_용어_관리.py` | 검토 대기 용어를 사람이 승인·반려 |
| `pages/11_감사_로그.py` | 로그인 시도와 관리자 행위, 잠금 풀기 (관리자만) |
| `reports.py` | 답이 나오면 임시로 넣고, 저장 버튼이 `is_saved` 를 켠다. 파일 없음 |
| `glossary.py` | 있으면 꺼내 쓰고 +1, 없으면 LLM 해설을 등록(pending). 질문 속 용어는 검색 맥락으로 |
| `exporter.py` | 하나의 중간 형식에서 HTML(항상)·DOCX·PPTX·PDF |
| `schema.sql` | PostgreSQL 용 같은 스키마 |

## 해보기 (DB·모델 없이)

```bash
pip install streamlit bcrypt python-docx python-pptx
# 15장·16장의 가짜 코퍼스 (없으면 만든다 — 16장 README 참고)
export DEFAULT_ADMIN_PASSWORD=책읽는농부
streamlit run Home.py --server.port 8501
```

브라우저에서 `admin / 책읽는농부` 로 들어간다. 논문 검색에 질문을 넣으면 가짜 코퍼스에서 근거를 찾아 답 모양을 만들고,
용어 해설이 붙고(해설은 "미작성 — 검토 필요"), 저장 버튼을 누르면 "내 보고서"에 남고, 용어 관리에서 승인할 수 있고, 감사 로그에 로그인이 찍힌다.

## 실제로 (Spark2)

```bash
export PG_DSN=... LLM_BASE_URL=... QWEN3_RERANKER_URL=... PAPERS_TABLE=papers_fig   # 16장과 같게
psql "$PG_DSN" -f schema.sql
streamlit run Home.py --server.port 8501 --server.address 0.0.0.0
```

## 정직하게

- 실제 앱은 화면이 열한 개이고 논문 검색 화면 하나가 9만 자, AI 검색 화면은 22만 자다. 여기서는 18장이 말한 것만 남겼다: 로그인·역할·검색·보고서·용어·출력.
- 실제로는 처음에 앱이 셋(8501·8502·8503)이었고, 검색·관리 앱에 로그인이 없어 2026-08-20 에 껐다. 이 예제는 처음부터 하나다.
- 실제 `user_reports.figure_ids` 는 PostgreSQL 배열이다. SQLite 에서는 쉼표로 이어 붙여 흉내 낸다.
- PDF 는 `reportlab` 이 있어야 하고 한글 글꼴을 찾아야 한다. 없으면 HTML 을 대신 돌려주고 경고한다.
- 이 저장소에서 자동 검증한 것: 인증(해시·잠금·기록), 보고서 저장·표시·불러오기, 용어 등록·꺼내 쓰기·검토, 출력 4종의 바이트 생성, 그리고 화면 파일들의 문법. 브라우저에서 눌러 보는 것은 손으로.
