-- 02_indexes.sql — 벡터에 HNSW 인덱스를 세운다 (11장 "벡터에 인덱스를 세운다")
--
-- 실행:
--   docker exec -i rag-postgres psql -U <db_사용자> -d ragdb < 02_indexes.sql
--
-- 왜 인덱스? 청크가 수백만 개로 늘면 매번 전부와 비교하는 건 너무 느리다.
-- HNSW는 '가까운 이웃을 빠르게 추려내는 지름길'이다.
--
-- ⏱ 팁: 인덱스는 데이터를 어느 정도 넣은 뒤 만드는 게 효율적이다.
--        빈 테이블에 미리 만들기보다, 적재 후 한 번에 세우는 편이 낫다.

-- 코사인 유사도 기준 HNSW 인덱스
--   m, ef_construction 은 정확도/속도/메모리의 트레이드오프. 기본값에서 시작해 조정.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 검색 시 정확도를 높이려면 세션에서 ef_search 를 올린다 (느려지지만 더 정확)
--   SET hnsw.ef_search = 100;

-- ── 데이터가 크게 불어난 뒤 (재구축) ───────────────────
-- 인덱스가 헐거워져 검색 품질이 떨어지면 다시 세운다.
--   REINDEX INDEX CONCURRENTLY idx_chunks_embedding;
--
-- 데이터가 자라면 색인도 다시 손봐야 한다 — DB는 함께 자라며 돌보는 것.
