# 19장. 스스로 도구를 쓰게 하다 — MCP와 에이전틱

두뇌(12장)에 손을 달아 준다. 모델이 도구를 고르고, 코드가 실행하고, 결과를 보고 다시 고른다.

```
agent.py ─ 루프(≤10바퀴, 예산 ≤14회) ─┬─ StdioMcpClient ─ mcp_server_papers.py (search_papers · get_paper_details)
   전략 프롬프트 + 절대 규칙            └─ LocalTools ─ tools.py (ChEMBL · 분자 · NCBI · AlphaFold · DiffDock)
   인용 검증 가드 · 예산 가드             check_servers() 상태 표시등
```

## 파일

| 파일 | 역할 |
|---|---|
| `mcp_server_papers.py` | MCP 서버 뼈대. `tools/list` · `tools/call` 을 JSON-RPC 로. 표준입출력 또는 `--http 포트`. 16장 검색기를 감싼다 |
| `mcp_clients.py` | 세 통로: `StdioMcpClient`(프로세스를 띄워 한 줄씩), `HttpMcpClient`(POST), `LocalTools`(같은 프로세스). `check_servers()` 상태 표시등 |
| `tools.py` | 도구 등록부 여덟: 스키마 + 실행 함수. `AGENT_FAKE=1` 이면 바깥 API 대신 정해진 가짜 결과 |
| `agent.py` | 루프, 전략 시스템 프롬프트, 절대 규칙, 예산(총 14 · 도구별), 인용 검증 가드. `FakeLLM` 은 전략을 따르는 각본 |
| `mcpo-config.example.json` | MCP 서버들을 HTTP API 로 내놓는 mcpo 설정 본보기 |

## 해보기 (LLM·DB·바깥 API 없이)

15장의 가짜 코퍼스가 있어야 한다 (16장 README 참고).

```bash
python mcp_clients.py                                   # stdio 로 논문 서버를 띄워 도구 목록 + 검색 한 번
python agent.py "설포라판과 부티르산의 HDAC 억제 시너지와 표적은?" --fake
```

가짜 모델은 전략대로 `search_papers` 넷 → `ncbi_search` → ChEMBL 양쪽 → AlphaFold → DiffDock 순으로 부르고 답을 쓴다.
답에 일부러 **검색되지 않은 논문 번호** 하나를 섞어 두었다. 가드가 그것을 "인용 무효"로 표시하는 것을 보라.
규칙은 프롬프트에만 두지 않는다 — 코드가 한 번 더 지킨다.

## 실제로 (Spark2)

```bash
export PG_DSN=... LLM_BASE_URL=... QWEN3_RERANKER_URL=... PAPERS_TABLE=papers_fig     # 16장과 같게
export NVIDIA_API_KEY=...                                                          # 없으면 dock_molecule 이 목록에서 빠진다
python agent.py "낙산균이 장뇌축과 어떤 관련이 있는가"
```

## 정직하게

- 실제 시스템의 도구는 서른 개 남짓(논문 넷 · 지식 그래프 셋 · ChEMBL 넷 · 화학 계산 다섯 · NCBI 셋 · AlphaFold 열아홉 · BioNeMo 셋 · 제품 둘). 여기서는 뼈대 여덟만.
- 실제 시스템 프롬프트는 이보다 훨씬 길다(논문 유형 분류 규칙, 인용-본문 일치 규칙, 상위 60편 규칙 …). 여기엔 절대 규칙 넷과 전략의 뼈대만.
- 실제 AlphaFold 서버는 TypeScript 로 된 별도 프로세스(도구 19개)이고, NCBI 는 HTTP(:8787). 이 예제의 `alphafold_get_structure` · `ncbi_search` 는 같은 공개 API 를 부르는 얇은 함수다.
- **웹 검색(SearXNG)과 대화 창(Open WebUI)은 넣지 않았다.** 써 봤고, 접었다. 검색 엔진은 세상에 더 좋은 것이 많아서, 대화 창은 그때 Qwen 과 잘 붙지 않아 프롬프트가 닿지 않고 환각이 심해서. 붙여서 답이 나온다고 되는 것이 아니다 — 규칙이 모델까지 어떻게 전달되는지를 알고 써야 한다.
- 단백질 구조와 도킹의 결과는 이 코드도 책도 **검증하지 않는다.** "도구가 이렇게 말했다"까지다. 그 답을 판단하는 것은 그 분야를 아는 사람의 몫이다.
- 이 저장소에서 자동 검증한 것: stdio·HTTP 두 통로로 MCP 서버 호출, 상태 표시등, 가짜 각본으로 도는 루프(예산 · 도구별 한도 · 인용 가드). 실제 LLM 툴 콜은 서버에서 확인해야 한다.
