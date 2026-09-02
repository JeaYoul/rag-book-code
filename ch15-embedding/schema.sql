-- schema.sql — 15장이 채우는 그릇 (11장의 두 테이블을 실제 열 이름으로 넓힌 것)
--
--   psql "$PG_DSN" -f schema.sql
--
-- 실제 시스템의 chunks 는 뷰이고 실체는 chunks_fig 이지만, 여기서는 이름을 단순하게 둔다.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- 글자 유사도 (16장)
CREATE EXTENSION IF NOT EXISTS pg_prewarm;   -- 인덱스를 미리 메모리에 (20장)

CREATE TABLE IF NOT EXISTS papers (
    paper_id      VARCHAR(200) PRIMARY KEY,   -- PMCID. 기본 키라 다시 넣어도 두 번 안 들어간다
    title         TEXT NOT NULL,
    authors       TEXT,
    abstract      TEXT,
    doi           TEXT,
    pmid          TEXT,
    journal       VARCHAR(500),
    year          INTEGER,
    source        VARCHAR(20) DEFAULT 'PMC',
    parse_status  VARCHAR(20) DEFAULT 'pending',
    parsed_at     TIMESTAMP,
    figure_count  INTEGER DEFAULT 0,
    table_count   INTEGER DEFAULT 0,
    chunk_count   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id             VARCHAR(600) PRIMARY KEY,
    paper_id             VARCHAR(200) REFERENCES papers(paper_id) ON DELETE CASCADE,
    chunk_type           VARCHAR(20),        -- text | figure_caption | table_data
    section              TEXT,
    context_header       TEXT,               -- "논문 제목 | 섹션 경로"
    content              TEXT,               -- 임베딩용 (머리글 포함)
    content_for_llm      TEXT,               -- LLM 에 건넬 글 (본문만)
    char_count           INT,
    is_reference_section BOOLEAN DEFAULT FALSE,
    figure_id            VARCHAR(250),
    table_id             VARCHAR(250),
    table_data           JSONB,
    embedding            vector(1024),       -- bge-m3
    content_tsv          tsvector,           -- 글자 검색용 (트리거가 채운다)
    created_at           TIMESTAMP DEFAULT now()
);

-- 벡터 인덱스 — 실제 값 그대로. ef_construction 을 기본값(64)보다 올렸다
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- 글자 인덱스 — 섹션 제목은 A, 본문은 B 가중치
CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.content_tsv :=
        setweight(to_tsvector('english', COALESCE(NEW.section, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_tsv_trigger ON chunks;
CREATE TRIGGER chunks_tsv_trigger
    BEFORE INSERT OR UPDATE OF section, content ON chunks
    FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();

CREATE INDEX IF NOT EXISTS chunks_content_tsv_idx ON chunks USING gin (content_tsv);

-- 자주 거는 조건들
CREATE INDEX IF NOT EXISTS chunks_paper_id_idx   ON chunks (paper_id);
CREATE INDEX IF NOT EXISTS chunks_paper_type_idx ON chunks (paper_id, chunk_type);
CREATE INDEX IF NOT EXISTS chunks_figure_id_idx  ON chunks (figure_id) WHERE figure_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_table_id_idx   ON chunks (table_id)  WHERE table_id  IS NOT NULL;
