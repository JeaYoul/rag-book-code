# 17장. 재고, 고치고, 다시 재고 — 평가와 튜닝

문제지를 고정하고, 시스템에 시험을 보게 하고, 두 개의 자로 재고, 점수를 **같은 파일에 적어 둔다.**

```
testset.json ─ run_exam.py ─→ results/open.json ─┬─ verify_citations.py  (자 ②: 인용이 실재하는가 — SQL)
                                                  ├─ evaluate.py          (자 ①: 네 지표, 심판 LLM)
                                                  └─ rerank_distribution.py (문턱을 어디에 둘까)
```

## 파일

| 파일 | 역할 |
|---|---|
| `testset.example.json` | 문제지 틀. 질문 + 모범답 + 분야. **당신 분야의 30문항을 손으로 써서** `testset.json` 으로 |
| `run_exam.py` | 시험. `--mode closed`(LLM 혼자) / `open`(16장 검색으로 근거를 주고). 결과를 JSON 으로 |
| `verify_citations.py` | 답의 PMC 번호가 DB(또는 코퍼스)에 실재하는지. 사람도 모델도 끼지 않는 자 |
| `evaluate.py` | 충실성(주장 단위) · 관련성 · 근거 정밀도 · 근거 재현율. 최저선 0.60/0.65/0.50/0.55. 점수를 결과 파일에 덧붙인다 |
| `rerank_distribution.py` | 리랭커 점수 분포와 문턱(기본 0.35), 최소 3편 안전망 |

## 해보기 (DB·모델 없이 — 흐름만)

15장·16장의 가짜 코퍼스가 있어야 한다.

```bash
cd ../ch15-embedding && python ../ch14-parsing/nxml_parser.py ../ch14-parsing/sample/PMC000001/PMC000001.nxml --out packages/PMC000001 \
  && python chunker.py packages/PMC000001 --out chunks/PMC000001.jsonl && python embed.py chunks/PMC000001.jsonl --out-dir embedded --fake
cd ../ch17-eval
python run_exam.py testset.example.json --mode open --out results/open.json --memory ../ch15-embedding/embedded/*.jsonl --fake
python verify_citations.py results/open.json --known-from ../ch15-embedding/embedded/*.jsonl
python evaluate.py results/open.json --fake
python rerank_distribution.py results/open.json
```

가짜 답에는 일부러 없는 논문 번호(`PMC0000000`)를 하나 섞어 두었다. 검증기가 그것을 잡는 것을 보라.

## 실제로 (Spark2)

```bash
export PG_DSN=... LLM_BASE_URL=... QWEN3_RERANKER_URL=... PAPERS_TABLE=papers_fig     # 16장과 같게
export JUDGE_BASE_URL=http://<다른 모델>/v1 JUDGE_MODEL=...   # 심판은 시험 보는 모델과 다르게
python run_exam.py testset.json --mode closed --out results/closed.json
python run_exam.py testset.json --mode open   --out results/open.json --pg
python verify_citations.py results/open.json --pg
python evaluate.py results/open.json
python rerank_distribution.py results/open.json
```

## 정직하게

- 실제 시스템에서 네 지표의 채점은 대부분 **클로드 대화창에서** 했다. 보고서 화면을 찍어 올리면 클로드가 채점하고 이유를 말해 줬다. 이 `evaluate.py` 는 그 채점을 서버 안으로 들여와 **결과 파일에 남기기 위해** 다시 쓴 것이다. 실제 서버의 `ragas_evaluator_v2.py` 와 발상(주장 단위 충실성, 최저선)은 같고, 코드는 다르다.
- 인용 검증기는 실제 `ragas_eval_rag.py` 의 `verify_citations` 와 같은 방식이다.
- `--fake` 심판은 낱말 겹침이라 뜻을 모른다. 흐름을 볼 때만 쓴다.
- 점수 자체는 책에 적지 않는다. 문제지와 심판이 다르면 견줄 수 없는 숫자이기 때문이다. 이 도구가 주는 것은 **어느 칸이 낮은가**다.
