# 16장. 찾아내기 — 검색 시스템

질문 하나가 조각 다섯이 되기까지. 16장 그림 그대로다.

```
질문 ─ query_rewrite (옮기고 · 넓히고 · 쪼개고) ─┬─ 한국어 판 벡터 검색 20 ─┐
                                                  └─ 영어 판 벡터 검색 20 ──┴─ 합침 (0.5)
     → rerank (Qwen3-Reranker-8B :8090 → 안 되면 bge) → 논문당 둘 규칙 → 5개 → LLM
```

## 파일

| 파일 | 역할 |
|---|---|
| `query_rewrite.py` | 용어표 번역(남으면 LLM), 동의어 사전(원료명은 뺌), 복합 질문 판정(다섯 신호 중 둘), LLM 분해(JSON 2~6개, 온도 0, seed 42), 메타 단어 제거. LLM 이 없으면 규칙으로 물러선다 |
| `search.py` | `PgBackend`(pgvector SQL, 참고문헌 제외 · 벡터+키워드 7:3) 와 `MemoryBackend`(DB 없이 numpy). 두 벌 검색 `retrieve_unified_chunks` |
| `rerank.py` | Qwen HTTP 주력 → bge CrossEncoder 폴백, 앞 8,000자. `FakeReranker`(실습). `deduplicate_chunks` 논문당 둘(둘째는 0.95↑) |
| `pipeline.py` | 전체 흐름. 서브쿼리마다 15 → 10 → 5. 컨텍스트는 머리글 없는 글 + 출처. `--ask` 면 LLM 에게 |

## 해보기 (DB·모델 없이)

15장에서 `--fake` 로 만든 embedded jsonl 이 있으면 바로 된다.

```bash
cd ../ch15-embedding
python ../ch14-parsing/nxml_parser.py ../ch14-parsing/sample/PMC000001/PMC000001.nxml --out packages/PMC000001
python ../ch14-parsing/nxml_parser.py ../ch14-parsing/sample/PMC000003/PMC000003.nxml --out packages/PMC000003
python chunker.py packages/PMC000001 --out chunks/PMC000001.jsonl
python chunker.py packages/PMC000003 --out chunks/PMC000003.jsonl
python embed.py chunks/*.jsonl --out-dir embedded --fake
cd ../ch16-retrieval
python query_rewrite.py "설포라판의 Nrf2 경로와 HDAC 억제, 그리고 면역 조절 기전을 설명하라"
python pipeline.py "설포라판과 부티르산의 HDAC 억제 효과는?" --memory ../ch15-embedding/embedded/*.jsonl --fake
```

가짜 벡터는 뜻이 없으니 순위는 의미가 없다. 보는 것은 **흐름**이다. 두 벌이 합쳐지고, 리랭커가 순위를 바꾸고, 논문당 둘 규칙이 걸러 내는 것.

## 실제로 (Spark2)

```bash
export PG_DSN=postgresql://ai_user:비밀번호@localhost:5432/ai_research_db
export LLM_BASE_URL=http://localhost:4000/v1          # 13장의 게이트웨이
export QWEN3_RERANKER_URL=http://localhost:8090/v1/rerank
export PAPERS_TABLE=papers_fig                      # 실제 DB 의 논문 테이블 이름
python pipeline.py "낙산균이 대장 염증에 미치는 효과와 기전은?" --pg --ask
```

## 정직하게

- 실제 시스템의 "하이브리드"는 **한국어 판 + 영어 판** 두 벌 검색이다. 벡터+키워드(7:3)는 `PgBackend.hybrid_vector_bm25` 에 있지만, 실제로는 평가(17장)에서 쓴다.
- 티어 가중치(1.30 / 1.15)는 코드에 있으나 등급을 매기지 못해 지금은 전부 1.0 — 이 예제에는 넣지 않았다.
- 리랭커 서버의 `/v1/rerank` 응답 모양은 실제 서버(12장 `reranker_server.py`)에 맞췄다. 다른 서버면 `QwenHttpReranker.score` 만 고치면 된다.
- 이 저장소에서 자동 검증한 것: 리라이팅 규칙, 두 벌 병합, 가짜 리랭커, 논문당 둘 규칙, 메모리 백엔드 전체 흐름. `PgBackend` 와 진짜 리랭커·LLM 은 서버에서 확인해야 한다.
