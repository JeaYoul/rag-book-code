#!/usr/bin/env python3
"""
mcp_server_papers.py — 논문 검색을 MCP 서버 모양으로 (19장 "MCP란 무엇인가")

MCP 의 뼈대는 두 함수다:  tools/list (내가 가진 도구 목록)  ·  tools/call (그 중 하나를 실행)
말은 JSON-RPC 로 한다. 통로는 둘 다 지원한다:

    python mcp_server_papers.py                 # 표준입출력 — 한 줄에 요청 하나, 한 줄에 응답 하나
    python mcp_server_papers.py --http 8787     # HTTP — POST / 에 JSON-RPC

도구: search_papers · get_paper_details.  16장의 검색기(MemoryBackend 또는 PgBackend)를 그대로 부른다.
SDK 없이 규약만 흉내 냈다. 실제 서버는 mcp 패키지를 쓴다 — 하는 일은 같다.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _s in (sys.stdin, sys.stdout):                       # 통로가 글자라서 — 양쪽 다 UTF-8 로 못 박는다
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")
sys.path.insert(0, str(HERE.parent / "ch16-retrieval"))
sys.path.insert(0, str(HERE.parent / "ch15-embedding"))

TOOLS = [
    {"name": "search_papers", "description": "내 논문 DB 에서 질문과 가까운 조각을 찾는다 (16장 파이프라인).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}},
                     "required": ["query"]}},
    {"name": "get_paper_details", "description": "paper_id 로 논문 한 편의 조각들을 돌려준다.",
     "inputSchema": {"type": "object", "properties": {"paper_id": {"type": "string"}}, "required": ["paper_id"]}},
]


class PaperTools:
    def __init__(self):
        from embed import Encoder
        if os.getenv("PG_DSN"):
            from search import PgBackend
            self.backend, self.encoder, self.fake = PgBackend(), Encoder(fake=False), False
        else:
            from search import MemoryBackend
            files = glob.glob(os.getenv("MEMORY_CORPUS", str(HERE.parent / "ch15-embedding" / "embedded" / "*.jsonl")))
            self.backend, self.encoder, self.fake = MemoryBackend(files), Encoder(fake=True), True

    def search_papers(self, query, top_k=5):
        from pipeline import enhanced_search
        from rerank import FakeReranker
        res = enhanced_search(query, self.backend, self.encoder, top_k=top_k, use_llm=not self.fake,
                              reranker=FakeReranker() if self.fake else None)
        return [{"paper_id": c["paper_id"], "title": c.get("paper_title", ""), "section": c.get("section", ""),
                 "score": round(c.get("rerank_score", 0), 3), "snippet": c["content"][:300]} for c in res["merged_chunks"]]

    def get_paper_details(self, paper_id):
        if hasattr(self.backend, "chunks"):
            hits = [c for c in self.backend.chunks if c["paper_id"] == paper_id]
            return {"paper_id": paper_id, "chunks": [{"section": c.get("section", ""), "content": c["content"][:500]} for c in hits[:10]]}
        return {"paper_id": paper_id, "note": "PgBackend: 실제 서버는 papers_fig/chunks 에서 읽는다"}


# ---------------------------------------------------------------- JSON-RPC

def handle(request, tools: PaperTools):
    """요청 하나 → 응답 하나. MCP 의 세 메서드만."""
    rid, method, params = request.get("id"), request.get("method"), request.get("params") or {}
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "papers", "version": "0.1"}, "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name, args = params["name"], params.get("arguments") or {}
            fn = getattr(tools, name, None)
            if fn is None:
                raise ValueError(f"unknown tool: {name}")
            result = {"content": [{"type": "text", "text": json.dumps(fn(**args), ensure_ascii=False)}]}
        else:
            raise ValueError(f"unknown method: {method}")
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": f"{type(e).__name__}: {e}"}}


def serve_stdio(tools):
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle(json.loads(line), tools)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def serve_http(tools, port):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):                                    # 상태 표시등이 두드리는 곳
            self._send(200, {"ok": True, "server": "papers"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self._send(200, handle(json.loads(self.rfile.read(n) or b"{}"), tools))

        def _send(self, code, body):
            b = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--http", type=int, default=0, help="포트를 주면 HTTP 로, 없으면 표준입출력으로")
    a = ap.parse_args()
    t = PaperTools()
    if a.http:
        serve_http(t, a.http)
    else:
        serve_stdio(t)
