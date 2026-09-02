# 15장. 의미를 숫자로 — 임베딩과 적재

14장의 패키지를 조각(청크)으로 자르고, bge-m3 로 숫자로 바꾸고, PostgreSQL 에 넣는다.

```
packages/<ID>/ ─ chunker.py ─→ chunks/<ID>.jsonl ─ embed.py ─→ embedded/<ID>.embedded.jsonl ─ load.py ─→ papers · chunks
                                                                                   backfill_embeddings.py ─→ embedding IS NULL 인 것만 채움
```

## 파일

| 파일 | 역할 |
|---|---|
| `chunker.py` | 조각 만들기. 본문(text)은 섹션 단위로, 그림 캡션(figure_caption)과 표(table_data)는 제 조각으로. 머리글 "제목 \| 섹션 경로", 참고문헌 표시. 첫 파싱의 `simple_chunker`(500자·100자 겹침) 그대로 포함 |
| `embed.py` | bge-m3, 정규화, 배치 32. `--fake` 면 모델 없이 결정적 가짜 벡터 (실습용) |
| `schema.sql` | `papers`·`chunks` 테이블, HNSW(m=16, ef_construction=200), tsvector 트리거 + GIN, pg_trgm·pg_prewarm |
| `load.py` | `execute_values` 로 논문 한 편의 조각을 한 번에. `--dry-run` 이면 DB 없이 보낼 행만 보여 준다 |
| `backfill_embeddings.py` | 벡터가 비어 있는 조각만 골라 채운다 — 이것이 곧 체크포인트. 배치 32, 커밋 256 |
| `count.sql` | 끝났는지 세어 보는 쿼리. 실제 값이 주석에 있다 |

## 해보기

**1. 14장 패키지를 조각으로.** (14장의 `sample` 로 먼저 패키지를 만들어 둔다)

```bash
python ../ch14-parsing/nxml_parser.py ../ch14-parsing/sample/PMC000001/PMC000001.nxml --out packages/PMC000001
python chunker.py packages/PMC000001 --out chunks/PMC000001.jsonl
python chunker.py packages/PMC000001 --out chunks/PMC000001.first.jsonl --chunk-size 500   # 첫 파싱 규칙과 비교
```

**2. 숫자로.** 모델을 내려받기 전에 `--fake` 로 흐름부터.

```bash
python embed.py chunks/PMC000001.jsonl --out embedded/PMC000001.embedded.jsonl --fake
python embed.py chunks/PMC000001.jsonl --out embedded/PMC000001.embedded.jsonl          # 진짜 bge-m3
```

**3. 넣는다.**

```bash
export PG_DSN=postgresql://ai_user:비밀번호@localhost:5432/ai_research_db
psql "$PG_DSN" -f schema.sql
python load.py embedded/PMC000001.embedded.jsonl --meta-dir packages/ --dry-run   # DB 없이 확인
python load.py embedded/PMC000001.embedded.jsonl --meta-dir packages/             # 실제 적재
python backfill_embeddings.py          # 빈 벡터가 있으면 채운다
psql "$PG_DSN" -f count.sql            # 세어 본다
```

**4. 검색이 되는가.** 한국어로 묻고 영어 조각이 올라오면 이 장은 끝이다.

```sql
-- embed.py 의 encode_query 로 질문 벡터를 만들어 아래 :qvec 자리에 넣는다
SELECT chunk_id, chunk_type, section, left(content_for_llm, 120)
FROM chunks WHERE NOT is_reference_section
ORDER BY embedding <=> :qvec LIMIT 5;
```

## 정직하게

- 실제 시스템은 `chunks` 가 뷰이고 실체는 `chunks_fig` 이며, 열이 이보다 많다(`section_id`, `chunk_index`, `page_range`, `has_figure`, `linked_chunk_ids` …). 여기서는 15장에서 말한 열만 남겼다.
- 실제 본문 조각의 평균은 약 1,100자다. `chunker.py` 기본값 1100 은 그 평균을 흉내 낸 값이지, 실제 재파싱 코드의 규칙 그대로는 아니다. 첫 파싱의 500/100 은 실제 코드 그대로다.
- 이 저장소에서 자동으로 검증한 것은 청킹, 가짜 벡터 임베딩, `--dry-run` 적재, SQL 문법까지다. 실제 PostgreSQL 적재와 bge-m3 는 서버에서 돌려 확인해야 한다.
- 논문 요약을 머리글로 얹는 LLM 방식(코드에는 있으나 DB 에는 미적용)은 이 예제에 넣지 않았다.
