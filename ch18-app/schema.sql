-- schema.sql — 18장 앱의 테이블 (PostgreSQL). 실제 서버의 열 이름을 따랐고, 열은 줄였다.
CREATE TABLE IF NOT EXISTS users (
    user_id        SERIAL PRIMARY KEY,
    username       VARCHAR(50) UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,                       -- bcrypt
    role           VARCHAR(20) DEFAULT 'researcher',    -- researcher | core | admin
    full_name      TEXT, dept TEXT,
    is_active      BOOLEAN DEFAULT true,
    login_failures INTEGER DEFAULT 0,                   -- 5 이면 잠김
    last_login     TIMESTAMP,
    created_at     TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY, username VARCHAR(100), success BOOLEAN, reason TEXT, source_app TEXT, client_ip TEXT,
    attempted_at TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS admin_actions (
    id SERIAL PRIMARY KEY, actor VARCHAR(100), action TEXT, target TEXT, detail TEXT, acted_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_actions_time ON admin_actions (acted_at DESC);
CREATE TABLE IF NOT EXISTS user_reports (
    report_id      SERIAL PRIMARY KEY,
    username       VARCHAR(100) NOT NULL,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL,
    figure_ids     TEXT[] DEFAULT '{}',
    table_ids      TEXT[] DEFAULT '{}',
    chembl_summary TEXT,
    is_saved       BOOLEAN DEFAULT false,
    created_at     TIMESTAMP DEFAULT now(),
    updated_at     TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ur_username ON user_reports (username);
CREATE INDEX IF NOT EXISTS idx_ur_saved ON user_reports (is_saved);
CREATE TABLE IF NOT EXISTS glossary_terms (
    id                SERIAL PRIMARY KEY,
    term_en           VARCHAR(200) UNIQUE NOT NULL,
    term_ko           VARCHAR(200),
    definition_ko     TEXT, definition_en TEXT,
    category          VARCHAR(100),
    source_pmcids     TEXT[],
    source_page       VARCHAR(50) NOT NULL,
    used_by_pages     TEXT[] DEFAULT '{}',
    usage_count       INTEGER DEFAULT 1,
    review_status     VARCHAR(20) DEFAULT 'pending',    -- pending | approved | rejected
    reviewed_by       VARCHAR(100), reviewed_at TIMESTAMP,
    created_at        TIMESTAMP DEFAULT now(), updated_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_glossary_review_status ON glossary_terms (review_status);
CREATE TABLE IF NOT EXISTS chat_logs (
    id SERIAL PRIMARY KEY, username VARCHAR(100), query_text TEXT, response_text TEXT, mode VARCHAR(20),
    search_sec REAL, llm_sec REAL, created_at TIMESTAMP DEFAULT now()
);
