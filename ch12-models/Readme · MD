# 12장 — 여러 개의 모델

『산골 농부의 RAG 개발 야화』 12장에서 다룬 모델들을 띄우고 부르는 코드입니다.

> ⚠️ **먼저 읽어주세요**
> 모델 경로·포트·비밀 값은 `<이렇게>` 표시된 자리에 **당신의 값**을 넣으세요.
> 그대로 실행하면 동작하지 않습니다.

---

## 다섯 개의 모델, 다섯 개의 일

| 역할 | 모델 | 어디서 | 이 폴더의 코드 |
|---|---|---|---|
| 임베딩 | `BAAI/bge-m3` (1024차원) | Spark2 | `embed_example.py` |
| 레이아웃 분석 | `docling-layout-heron`, `docling-models` | Spark2 | (14장 파싱에서 사용) |
| 멀티모달 | `Qwen3-VL-8B-Instruct` | Spark2 | (14장 파싱에서 사용) |
| 리랭커 (주력) | `Qwen3-Reranker-8B` | Spark2 :8090 | `reranker_server.py` |
| 리랭커 (예비) | `BAAI/bge-reranker-v2-m3` | Spark2 | `reranker_with_fallback.py` |
| 메인 LLM | `Qwen3.5-122B-A10B` (int4/fp8) | Spark1 :8000 | ☞ [ch09-infra](../ch09-infra) |
| 게이트웨이 | LiteLLM | Spark2 :4000 | `litellm_config.yaml` |

> vLLM 실행 스크립트·systemd 유닛은 중복을 피해 **[ch09-infra](../ch09-infra)**에 있습니다.

---

## 파일

| 파일 | 무엇 |
|---|---|
| `reranker_server.py` | Qwen3 리랭커 HTTP 서버 (`/v1/rerank` 호환). **메모리 안전장치 포함** |
| `reranker_with_fallback.py` | 주력 실패 시 예비 리랭커로 넘기는 폴백 래퍼 |
| `litellm_config.yaml` | 흩어진 모델을 한 창구로 묶는 게이트웨이 설정 |
| `embed_example.py` | bge-m3로 벡터 만드는 최소 예제 |

---

## 준비물

```bash
pip install torch transformers fastapi uvicorn pydantic requests
pip install FlagEmbedding sentence-transformers   # 임베딩·예비 리랭커용
pip install litellm                                # 게이트웨이
```

---

## 실행

```bash
# 1) 리랭커 서버 (Spark2)
python3 reranker_server.py            # :8090

# 확인
curl -s http://localhost:8090/health

# 2) LiteLLM 게이트웨이 (Spark2)
litellm --config litellm_config.yaml --port 4000

# 확인
curl -s http://localhost:4000/v1/models

# 3) 임베딩 예제
python3 embed_example.py
```

---

## ⚠️ 메모리 안전장치 — 꼭 읽으세요

`reranker_server.py`에는 **직접 겪은 사고에서 나온 안전장치**가 들어 있습니다.
초기 버전에는 이 장치들이 없었고, 그 결과 리랭커가 통합 메모리를 모두 삼켜
**시스템 전체가 정지**했습니다. (자세한 이야기는 책의 운영 장에)

코드에 반드시 유지해야 할 것:

1. **`logits_to_keep=1`** — 이게 없으면 `logits[:, -1, :]`로 슬라이싱하기 **전에**
   전체 logits(배치 × 토큰수 × 어휘 15만)를 만듭니다. 긴 입력에서 수백 GB.
2. **`MAX_LENGTH`를 크게 잡지 말 것** — 32768은 위험합니다. 4096 권장.
3. **`use_cache=False`** — 리랭킹은 생성이 아니므로 캐시가 필요 없습니다.
4. **청크 분할 + 문서 수 상한** — 한 번에 다 넣지 말고 나눠 처리하고,
   상한을 넘으면 거절합니다.

> 성능보다 **안 죽는 것**이 먼저입니다.
