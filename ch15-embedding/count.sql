-- count.sql — 적재가 끝났는지는 세어 봐야 안다 (15장)
--
--   psql "$PG_DSN" -f count.sql
--
-- 실제 값 (2026-09): papers 98,381 · chunks 4,890,768
--   text 4,204,090 (avg 1,121자) · figure_caption 475,396 (avg 589) · table_data 211,282 (avg 1,582)
--   embedding IS NULL 411 · is_reference_section 66,705

-- 종류별 조각 수와 길이
SELECT chunk_type, count(*) AS n, round(avg(char_count)) AS avg_chars,
       min(char_count) AS min, max(char_count) AS max
FROM chunks GROUP BY 1 ORDER BY 2 DESC;

-- 논문 수, 논문당 조각 수
SELECT (SELECT count(*) FROM papers) AS papers,
       (SELECT count(*) FROM chunks) AS chunks,
       round((SELECT count(*) FROM chunks)::numeric / NULLIF((SELECT count(*) FROM papers), 0), 1) AS chunks_per_paper;

-- 아직 안 한 것 — 0 이면 끝난 것
SELECT count(*) AS chunks_without_vector FROM chunks WHERE embedding IS NULL;

-- 참고문헌 표시가 붙은 조각 (검색에서 거른다)
SELECT count(*) AS reference_chunks FROM chunks WHERE is_reference_section;

-- 머리글이 붙은 조각 비율
SELECT count(*) FILTER (WHERE coalesce(context_header, '') <> '') AS with_header,
       count(*) AS total FROM chunks;

-- 인덱스가 서 있는가
SELECT indexname, left(indexdef, 90) AS def FROM pg_indexes WHERE tablename = 'chunks' ORDER BY 1;
