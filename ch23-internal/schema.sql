-- schema.sql — 사내 데이터를 논문과 같은 방식으로 담는 뼈대 (23장)
--
--   psql "$PG_DSN" -f schema.sql
--
-- 이 파일에는 실제 제품도 문서도 들어 있지 않다. 구조만 있다.
-- 실제 시스템의 칸 이름과 스키마는 이 책에 적지 않기로 했다 (23장 "이 장에 쓰지 않은 것").
-- 여기 있는 것은 같은 방법을 자기 데이터에 쓰려는 사람을 위한 뼈대다.
--
-- 설계에서 가장 중요한 결정 둘:
--   1) 논문 · 제품 · 내부문서를 **같은 모양**으로 담는다 (본체 표 + 조각 표 + 벡터)
--      그래야 논문 검색에 쓴 코드를 그대로 쓸 수 있다. 15·16장의 그 코드다.
--   2) 그런데 **같은 자리에 담지 않는다.** 스키마를 갈라 둔다.
--      실제 시스템은 아직 한 자리에 있고, 그것이 3만 편을 아직 붓지 못한 이유 중 하나였다.

-- ============================================================ 분리
-- 사내 데이터는 별도 스키마에. 검색 한 번이 실수로 두 종류를 긁어 오지 않게.
CREATE SCHEMA IF NOT EXISTS internal;

-- 읽기 전용 역할과 관리 역할을 나눠 둔다 (최소 권한)
-- DO 블록으로 감싸 이미 있으면 넘어가게 한다
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'internal_reader') THEN
    CREATE ROLE internal_reader NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'internal_writer') THEN
    CREATE ROLE internal_writer NOLOGIN;
  END IF;
END $$;

REVOKE ALL ON SCHEMA internal FROM PUBLIC;
GRANT USAGE ON SCHEMA internal TO internal_reader, internal_writer;

-- ============================================================ 문서 등급
-- 23장에서 늦게 깨달은 것: 사람만 등급을 나누면 안 되고 문서에도 등급이 필요하다.
-- 한 덩어리로 보이는 자료 안에 공개된 것과 공개되지 않은 것이 섞여 있다.
-- 그리고 이 판단은 사람이 한다. 기계에 맡기지 않는다.
CREATE TYPE internal.sensitivity AS ENUM (
  'public',        -- 이미 학술지에 게재됐거나 등록 공개된 것 — 공개 데이터와 같이 다뤄도 된다
  'restricted',    -- 사내 열람 가능 — 밖으로 내보내면 안 된다
  'confidential'   -- 출원 전 자료 · 미공개 실험 기록 — 검색 대상에서 빼는 것도 검토한다
);

-- ============================================================ 본체
CREATE TABLE IF NOT EXISTS internal.documents (
  doc_id         TEXT PRIMARY KEY,
  doc_type       TEXT NOT NULL,              -- 'paper' | 'patent' | 'report' | 'scan'
  title          TEXT,
  year           INT,
  -- 등급은 반드시 사람이 넣는다. 기본값을 두지 않는 이유:
  -- 기본값이 있으면 넣는 것을 잊었을 때 조용히 어느 등급으로 들어간다.
  sensitivity    internal.sensitivity NOT NULL,
  classified_by  TEXT NOT NULL,              -- 누가 그 등급을 붙였는가
  classified_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_path    TEXT,                       -- 원본이 어디 있는가 (종이면 서류철 번호)
  ocr_confidence REAL,                       -- 스캔본이면 글자 인식 신뢰도. 낮으면 사람이 본다
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN internal.documents.sensitivity IS
  '사람이 붙인다. 기본값 없음 — 잊으면 넣지 못하게 하는 편이 낫다';

-- ============================================================ 조각
-- 논문 조각과 같은 모양이다 (15장). 다만 칸 둘이 더 있다.
CREATE TABLE IF NOT EXISTS internal.chunks (
  chunk_id     BIGSERIAL PRIMARY KEY,
  doc_id       TEXT NOT NULL REFERENCES internal.documents(doc_id) ON DELETE CASCADE,
  chunk_type   TEXT NOT NULL,                -- 'text' | 'claim' | 'table' | 'figure_caption'
  -- 특허 청구항은 통째로 한 조각이어야 한다. 반으로 자르면 뜻이 반이 되는 것이 아니라
  -- 아예 다른 뜻이 된다. 그래서 자르지 않았음을 표시해 둔다.
  is_atomic    BOOLEAN NOT NULL DEFAULT false,
  section      TEXT,
  content      TEXT NOT NULL,
  embedding    vector(1024),                 -- 15장의 그 모델과 같은 차원
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_internal_chunks_doc  ON internal.chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_internal_chunks_type ON internal.chunks (chunk_type);
CREATE INDEX IF NOT EXISTS idx_internal_chunks_vec
  ON internal.chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);

-- ============================================================ 등급으로 걸러진 뷰
-- 애플리케이션은 표를 직접 읽지 않고 이 뷰를 읽는다.
-- 코드 한 곳에서 실수해도 등급 밖의 것이 나가지 않게 하는 장치다.
CREATE OR REPLACE VIEW internal.chunks_public AS
  SELECT c.* FROM internal.chunks c
  JOIN internal.documents d USING (doc_id)
  WHERE d.sensitivity = 'public';

CREATE OR REPLACE VIEW internal.chunks_restricted AS
  SELECT c.* FROM internal.chunks c
  JOIN internal.documents d USING (doc_id)
  WHERE d.sensitivity IN ('public', 'restricted');

GRANT SELECT ON internal.chunks_public, internal.chunks_restricted TO internal_reader;
GRANT SELECT, INSERT, UPDATE ON internal.documents, internal.chunks TO internal_writer;
-- confidential 을 포함하는 뷰는 만들지 않았다. 필요해지면 그때 만들고, 그때 한 번 더 생각한다.

-- ============================================================ 제품
-- 논문 · 내부문서와 같은 모양. 실제 칸 구성은 이 책에 적지 않는다.
CREATE TABLE IF NOT EXISTS internal.products (
  product_id  TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS internal.product_chunks (
  chunk_id    BIGSERIAL PRIMARY KEY,
  product_id  TEXT NOT NULL REFERENCES internal.products(product_id) ON DELETE CASCADE,
  content     TEXT NOT NULL,
  embedding   vector(1024)
);

CREATE INDEX IF NOT EXISTS idx_product_chunks_vec
  ON internal.product_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);

-- ============================================================ 확인
-- 부은 뒤에 반드시 이것을 본다. 등급이 빈 문서가 있으면 부으면 안 된다.
--   SELECT sensitivity, count(*) FROM internal.documents GROUP BY sensitivity;
--   SELECT count(*) FROM internal.chunks WHERE embedding IS NULL;
--   SELECT count(*) FROM internal.chunks WHERE chunk_type='claim' AND NOT is_atomic;  -- 0이어야 한다
