# 11장 — 어디에 담을 것인가 (데이터베이스 설계)

『산골 농부의 RAG 개발 야화』 11장에서 다룬 두 데이터베이스(PostgreSQL + MongoDB)의
설치·스키마·인덱스 설정 묶음입니다.

> ⚠️ **먼저 읽어주세요**
> 비밀번호·DB 이름·벡터 차원 같은 값은 `<이렇게>` 표시된 자리에 **당신의 값**을 넣으세요.
> 비밀번호가 든 파일은 그대로 커밋하지 마세요. `.env`로 분리하고 `.gitignore`에 넣으세요.

---

## 두 개의 그릇

- **PostgreSQL + pgvector** — 논문 서지·구조·청크 벡터 (텍스트·검색의 심장)
- **MongoDB** — 그림·표 같은 무거운 바이너리

> 성격이 다른 것은 나눠 담는다. 가벼운 텍스트·벡터는 PostgreSQL, 무거운 바이너리는 MongoDB.
> 9장에서 Spark1/Spark2로 역할을 나눈 것과 같은 정신.

---

## 파일 목록

| 파일 | 무엇 |
|---|---|
| `docker-compose.yml` | 두 DB를 컨테이너로 띄운다 |
| `01_schema.sql`      | 데이터베이스·pgvector 확장·테이블 생성 |
| `02_indexes.sql`     | 벡터 HNSW 인덱스 세우기 |
| `config.example.env` | 비밀번호 등 설정 (복사해서 `.env`) |

---

## 실행 순서

```bash
# 0. 설정 준비
cp config.example.env .env      # .env 에 비밀번호 채우기

# 1. 두 DB 컨테이너 띄우기
docker compose up -d
docker compose ps

# 2. 스키마 생성 (DB·확장·테이블)
docker exec -i rag-postgres psql -U <db_사용자> -d ragdb < 01_schema.sql

# 3. 벡터 인덱스 생성 (데이터를 어느 정도 넣은 뒤 실행하는 게 효율적)
docker exec -i rag-postgres psql -U <db_사용자> -d ragdb < 02_indexes.sql
```

---

## 스키마 한눈에

```
PostgreSQL
  papers   ── 논문 서지·신원 (paper_id PK)
    │  1:N
  chunks   ── 의미 단위 조각 + 벡터 (paper_id FK, embedding vector)
  figures  ── 그림 참조 (paper_id FK, object_id → MongoDB)
  tables   ── 표 참조   (paper_id FK, object_id → MongoDB)

MongoDB
  figure/table 문서 ── 실제 이미지·바이너리 (object_id로 PostgreSQL과 연결)
```

핵심: 모든 chunk·figure·table은 자기 논문(paper_id)을 가리킨다.
그래서 검색된 어떤 조각도 '어느 논문의 것'인지 되짚어 출처를 달 수 있다. (3·10장의 '신원')

---

## 주의

- **벡터 차원**(`vector(1024)`)은 쓰는 임베딩 모델에 맞춰야 한다. bge-m3는 1024. (13장)
- **HNSW 인덱스**는 데이터가 어느 정도 쌓인 뒤 만드는 게 효율적이다. 크게 늘면 재구축한다.
- 비밀 값은 커밋 금지. `.env` → `.gitignore`.
