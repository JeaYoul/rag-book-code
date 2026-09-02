-- 01_schema.sql — 데이터베이스·pgvector 확장·테이블 생성 (11장)
--
-- 실행:
--   docker exec -i rag-postgres psql -U <db_사용자> -d ragdb < 01_schema.sql
--
-- ⚠️ vector(1024) 의 차원은 쓰는 임베딩 모델에 맞추세요. bge-m3 = 1024 (13장).

-- 벡터 기능을 켠다 (이 한 줄이 평범한 PostgreSQL을 벡터 DB로 바꾼다)
CREATE EXTENSION IF NOT EXISTS vector;

-- ── 논문의 신원과 서지 정보 ───────────────────────────
CREATE TABLE IF NOT EXISTS papers (
    paper_id    SERIAL PRIMARY KEY,
    pmid        TEXT,
    pmcid       TEXT,
    doi         TEXT,
    title       TEXT,
    authors     TEXT,
    year        INT,
    journal     TEXT,
    affiliation TEXT
);

-- ── 논문을 의미 단위로 자른 조각 + 그 조각의 벡터 ──────
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    SERIAL PRIMARY KEY,
    paper_id    INT REFERENCES papers(paper_id) ON DELETE CASCADE,  -- 어느 논문의 조각인가
    section     TEXT,                    -- 서론·방법·결과·논의…
    content     TEXT,                    -- 조각 본문 (+ 엮인 그림 캡션)
    embedding   vector(1024)             -- 의미의 숫자 (모델 차원에 맞춤)
);

-- ── 그림 참조 (실제 이미지는 MongoDB, 여기엔 위치·설명만) ──
CREATE TABLE IF NOT EXISTS figures (
    figure_id   SERIAL PRIMARY KEY,
    paper_id    INT REFERENCES papers(paper_id) ON DELETE CASCADE,
    caption     TEXT,
    object_id   TEXT     -- MongoDB의 실제 이미지 문서를 가리키는 열쇠
);

-- ── 표 참조 (실제 표 데이터는 MongoDB) ────────────────
CREATE TABLE IF NOT EXISTS tables (
    table_id    SERIAL PRIMARY KEY,
    paper_id    INT REFERENCES papers(paper_id) ON DELETE CASCADE,
    caption     TEXT,
    object_id   TEXT     -- MongoDB의 실제 표 문서를 가리키는 열쇠
);

-- 자주 쓰는 조회를 위한 보조 인덱스
CREATE INDEX IF NOT EXISTS idx_chunks_paper  ON chunks(paper_id);
CREATE INDEX IF NOT EXISTS idx_figures_paper ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_tables_paper  ON tables(paper_id);
CREATE INDEX IF NOT EXISTS idx_papers_pmid   ON papers(pmid);
