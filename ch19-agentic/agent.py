#!/usr/bin/env python3
"""
agent.py — 두뇌에 손을 달아 주다 (19장 "에이전틱 검색" · "다단계 추론")

    AGENT_FAKE=1 python agent.py "설포라판과 부티르산의 HDAC 억제 시너지와 표적은?"     # LLM·바깥 API 없이
    python agent.py "..."                                                          # 실제 (LLM_BASE_URL, PG_DSN …)

루프는 열 줄이다: 모델이 도구를 고른다 → 코드가 실행한다 → 결과를 돌려준다 → 다시 고른다. 최대 10바퀴.
그 위에 전략(순서·예산 ≤14회)과 절대 규칙(수치 추측 금지 · 검색된 논문만 인용 · 모르면 검색, 없으면 모른다)을 얹는다.
규칙은 프롬프트에만 두지 않는다 — 코드가 한 번 더 지킨다 (인용 검증 가드, 예산 가드).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mcp_clients import LocalTools, StdioMcpClient, check_servers   # noqa: E402
import tools as T                                                   # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

MAX_ITERATIONS = 10
TOOL_BUDGET = 14
PER_TOOL_BUDGET = {"search_papers": 6, "get_paper_details": 2, "chembl_search_compound": 2, "chembl_get_bioactivity": 2,
                   "analyze_molecule": 2, "ncbi_search": 2, "alphafold_get_structure": 1, "dock_molecule": 1}

AGENT_SYSTEM_PROMPT = """[★★★ 절대 규칙 — 다른 모든 지시보다 우선 ★★★]
1. 모르면 검색한다. 검색해도 없으면 "근거를 찾지 못했다"고 쓴다. 기억으로 채우지 않는다.
2. 수치를 추측·보간·생성하지 않는다. 위반 시 보고서 전체 무효.
3. 답에 인용하는 [논문N]은 반드시 search_papers 가 돌려준 paper_id 여야 한다. 기억 속 논문을 인용하지 않는다.
4. 인용한 논문의 결론과 어긋나는 주장을 하지 않는다. 사전 지식과 논문이 다르면 논문이 이긴다.

[도구 호출 전략]
질문을 받으면 먼저 4~5개의 영어 키워드 서브쿼리로 분해하라 (서로 다른 관점: 분자 메커니즘 / 세포·면역 / 임상 / 시너지).
1. search_papers 4~6회 (서브쿼리별)
2. 최신 동향이 필요하면 ncbi_search 1~2회
3. 화합물 질문이면 chembl_search_compound → chembl_get_bioactivity (비교 질문이면 양쪽 다), analyze_molecule 0~2회
4. 표적 단백질 구조가 필요하면 alphafold_get_structure 1회 → dock_molecule 0~1회
도구 호출 예산: 총 14회 이내. 더 부를 것이 없으면 답을 쓴다.

[답의 형식]
근거 논문 목록 · 화합물 활성 표 · (있으면) 구조·도킹 결과 — 도킹은 "도구가 이렇게 말했다"까지만.
맨 마지막에 "## 추가 탐색 제안" 섹션에 다음 질문 셋을 반드시 쓴다."""


# ---------------------------------------------------------------- 모델

class OpenAICompatLLM:
    def __init__(self):
        self.base = os.getenv("LLM_BASE_URL", "http://localhost:4000/v1")
        self.model = os.getenv("LLM_MODEL", "qwen")

    def chat(self, messages, tool_schemas):
        import requests
        r = requests.post(f"{self.base}/chat/completions", json={
            "model": self.model, "messages": messages, "tools": tool_schemas, "tool_choice": "auto",
            "temperature": 0.2, "max_tokens": 4096, "chat_template_kwargs": {"enable_thinking": False}}, timeout=300)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = [{"id": c.get("id", f"call_{i}"), "name": c["function"]["name"], "arguments": json.loads(c["function"].get("arguments") or "{}")}
                 for i, c in enumerate(msg.get("tool_calls") or [])]
        return {"content": msg.get("content") or msg.get("reasoning_content") or "", "tool_calls": calls, "raw": msg}


class FakeLLM:
    """모델 없이 — 전략을 그대로 따르는 각본. 루프와 가드가 어떻게 도는지 보여 준다."""

    def __init__(self, question):
        self.q = question
        subs = ["sulforaphane HDAC inhibition mechanism", "butyrate HDAC inhibition mechanism",
                "sulforaphane butyrate combination synergy", "HDAC class I target structure"]
        self.plan = [("search_papers", {"query": s, "top_k": 3}) for s in subs]
        self.plan += [("ncbi_search", {"query": "sulforaphane butyrate synergy 2026", "max_results": 3}),
                      ("chembl_search_compound", {"name": "sulforaphane"}), ("chembl_get_bioactivity", {"chembl_id": "CHEMBL0000"}),
                      ("chembl_search_compound", {"name": "butyrate"}), ("chembl_get_bioactivity", {"chembl_id": "CHEMBL0000"}),
                      ("alphafold_get_structure", {"uniprot_id": "Q13547"}),
                      ("dock_molecule", {"protein_pdb_url": "https://alphafold.ebi.ac.uk/files/AF-Q13547-F1-model_v4.pdb", "ligand_smiles": "CS(=O)CCCCN=C=S"})]
        self.step = 0
        self.seen_ids = []

    def chat(self, messages, tool_schemas):
        # 이전 도구 결과에서 paper_id 를 모아 둔다 (답을 쓸 때 인용하려고)
        for m in messages:
            if m.get("role") == "tool":
                self.seen_ids += re.findall(r"PMC\d+", m["content"])
        if self.step < len(self.plan):
            batch = self.plan[self.step:self.step + 2]           # 한 바퀴에 둘씩
            self.step += len(batch)
            return {"content": "", "tool_calls": [{"id": f"call_{self.step}_{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(batch)], "raw": None}
        ids = list(dict.fromkeys(self.seen_ids))[:3]
        cites = " ".join(f"[{i}]" for i in ids) or "(근거를 찾지 못했다)"
        answer = (f"## 답\n설포라판과 부티르산은 각각 HDAC 를 억제한다는 근거가 있다 {cites}. "
                  f"병용 시너지에 관한 직접 근거는 검색된 범위에서 찾지 못했다.\n"
                  f"이 문장은 검색되지 않은 논문을 인용한다 [PMC9999999].\n"           # 가드가 잡아야 한다
                  f"## 도킹\n도구가 이렇게 말했다: 결합 자세 신뢰도 0.62 — 맞는지는 사람이 확인한다.\n"
                  f"## 추가 탐색 제안\n1. 병용 in vivo 연구 2. 클래스 I HDAC 선택성 3. 용량 반응")
        return {"content": answer, "tool_calls": [], "raw": None}


# ---------------------------------------------------------------- 가드

def validate_citations(answer, allowed_ids):
    """절대 규칙 3 을 코드로 — search_papers 가 돌려주지 않은 PMC 인용은 표시한다."""
    cited = set(re.findall(r"PMC\d+", answer))
    bad = sorted(cited - set(allowed_ids))
    for b in bad:
        answer = answer.replace(f"[{b}]", f"[{b} — ⚠ 검색되지 않은 논문, 인용 무효]")
    return answer, bad


# ---------------------------------------------------------------- 루프

def run_agentic_search(question, llm, servers, progress=print):
    status = check_servers(servers)                                  # 상태 표시등
    progress("서버 상태: " + " · ".join(f"{k}:{'●' if v['alive'] else '○'}" for k, v in status.items()))
    alive = {k for k, v in status.items() if v["alive"]}
    schemas = [s for s in T.enabled_schemas() if _server_of(s["function"]["name"]) in alive]

    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}, {"role": "user", "content": question}]
    history, calls_used, per_tool, allowed_ids = [], 0, {}, set()

    for iteration in range(1, MAX_ITERATIONS + 1):
        progress(f"[반복 {iteration}/{MAX_ITERATIONS}] 모델 호출")
        reply = llm.chat(messages, schemas)
        if not reply["tool_calls"]:                                   # 더 부를 것이 없으면 답
            answer, bad = validate_citations(reply["content"], allowed_ids)
            return {"answer": answer, "invalid_citations": bad, "tool_calls": history, "iterations": iteration, "server_status": status}
        messages.append({"role": "assistant", "content": reply["content"] or None,
                         "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}} for c in reply["tool_calls"]]})
        for call in reply["tool_calls"]:
            name, args = call["name"], call["arguments"]
            if calls_used >= TOOL_BUDGET or per_tool.get(name, 0) >= PER_TOOL_BUDGET.get(name, 2):
                result = json.dumps({"error": f"예산 초과 — {name} 은 더 부를 수 없다. 지금까지의 결과로 답하라."}, ensure_ascii=False)
                progress(f"   ✗ {name} 예산 초과")
            else:
                calls_used += 1; per_tool[name] = per_tool.get(name, 0) + 1
                try:
                    result = servers[_server_of(name)].call_tool(name, args)
                except Exception as e:
                    result = json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
                progress(f"   → {name}({json.dumps(args, ensure_ascii=False)[:60]})  {calls_used}/{TOOL_BUDGET}")
                if name == "search_papers":
                    allowed_ids.update(re.findall(r"PMC\d+", result))   # 인용 허용 목록
            history.append({"name": name, "arguments": args, "result": result[:500]})
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": result[:6000]})
    return {"answer": "(반복 한도에 닿았다 — 지금까지의 도구 결과만 있다)", "invalid_citations": [], "tool_calls": history,
            "iterations": MAX_ITERATIONS, "server_status": status}


def _server_of(tool_name):
    return "papers" if tool_name in ("search_papers", "get_paper_details") else "external"


def build_servers():
    papers = StdioMcpClient([sys.executable, str(HERE / "mcp_server_papers.py")])        # 표준입출력 통로
    external = LocalTools(T.EXTERNAL, [s for s in T.SCHEMAS if s["function"]["name"] in T.EXTERNAL])   # 같은 프로세스
    return {"papers": papers, "external": external}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--fake", action="store_true", help="LLM·바깥 API 없이 각본으로 (AGENT_FAKE=1 과 같다)")
    a = ap.parse_args()
    if a.fake:
        os.environ["AGENT_FAKE"] = "1"; T.FAKE = True
    servers = build_servers()
    llm = FakeLLM(a.question) if (a.fake or T.FAKE) else OpenAICompatLLM()
    try:
        res = run_agentic_search(a.question, llm, servers)
    finally:
        servers["papers"].close()
    print(f"\n반복 {res['iterations']}바퀴 · 도구 {len(res['tool_calls'])}회")
    for h in res["tool_calls"]:
        print(f"  {h['name']:26s} {json.dumps(h['arguments'], ensure_ascii=False)[:50]}")
    if res["invalid_citations"]:
        print(f"⚠ 검색되지 않은 인용 {res['invalid_citations']} — 무효 표시함")
    print("\n" + res["answer"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
