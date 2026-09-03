#!/usr/bin/env python3
"""
mcp_clients.py — MCP 서버와 말하는 세 통로 (19장)

    StdioMcpClient   서버 프로세스를 내가 띄우고, 한 줄 쓰고 한 줄 읽는다   (AlphaFold 서버가 이렇게)
    HttpMcpClient    서버가 포트에서 기다리고, JSON-RPC 를 POST 한다         (NCBI 서버가 이렇게, :8787)
    LocalTools       같은 프로세스 안의 파이썬 함수 — 규약만 맞춘다           (논문 검색이 이렇게)

    check_servers()  상태 표시등 — 검색 전에 서버마다 살아 있는지. 죽은 도구는 이번 검색에서 뺀다.
"""
import json
import os
import subprocess
import sys
import time


class StdioMcpClient:
    def __init__(self, cmd, timeout=60):
        self.cmd, self.timeout, self.proc, self._id = cmd, timeout, None, 0

    def _start(self):
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=None, text=True, encoding="utf-8", bufsize=1)   # stderr 는 그대로 보인다 — 서버가 왜 죽었는지 알아야 한다
        self._send("initialize", {})

    def _send(self, method, params):
        if self.proc is None or self.proc.poll() is not None:
            if method != "initialize":
                self._start()                                   # 죽어 있으면 다시 띄운다 — 불사조의 프로세스 판
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        while True:                                              # JSON 이 아닌 줄(라이브러리가 찍은 잡음)은 건너뛴다
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("서버가 응답 없이 끊겼다 (stderr 를 보라)")
            if line.lstrip().startswith("{"):
                break
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(resp["error"]["message"])
        return resp["result"]

    def list_tools(self):
        if self.proc is None:
            self._start()
        return self._send("tools/list", {})["tools"]

    def call_tool(self, name, arguments):
        if self.proc is None:
            self._start()
        r = self._send("tools/call", {"name": name, "arguments": arguments})
        return r["content"][0]["text"]

    def is_available(self):
        try:
            self.list_tools(); return True
        except Exception:
            return False

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


class HttpMcpClient:
    def __init__(self, url, timeout=30):
        self.url, self.timeout, self._id = url, timeout, 0

    def _send(self, method, params):
        import requests
        self._id += 1
        r = requests.post(self.url, json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}, timeout=self.timeout)
        r.raise_for_status()
        resp = r.json()
        if "error" in resp:
            raise RuntimeError(resp["error"]["message"])
        return resp["result"]

    def list_tools(self):
        return self._send("tools/list", {})["tools"]

    def call_tool(self, name, arguments):
        return self._send("tools/call", {"name": name, "arguments": arguments})["content"][0]["text"]

    def is_available(self):
        try:
            import requests
            return requests.get(self.url, timeout=5).status_code == 200      # GET 한 번 — 3월에 이렇게 바꿨다
        except Exception:
            return False


class LocalTools:
    """같은 프로세스 안 — 함수 사전 하나가 서버 노릇을 한다."""

    def __init__(self, functions: dict, schemas: list):
        self.functions, self.schemas = functions, schemas

    def list_tools(self):
        return self.schemas

    def call_tool(self, name, arguments):
        return json.dumps(self.functions[name](**arguments), ensure_ascii=False)

    def is_available(self):
        return True


def check_servers(servers: dict) -> dict:
    """{이름: 클라이언트} → {이름: 살아 있는가}. 화면 위의 표시등."""
    status = {}
    for name, client in servers.items():
        t0 = time.time()
        status[name] = {"alive": client.is_available(), "ms": int((time.time() - t0) * 1000)}
    return status


if __name__ == "__main__":
    # 데모: 논문 서버를 stdio 로 띄워 도구 목록을 받고 한 번 부른다
    c = StdioMcpClient([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server_papers.py")])
    print("tools:", [t["name"] for t in c.list_tools()])
    print(c.call_tool("search_papers", {"query": "sulforaphane HDAC", "top_k": 2})[:300])
    c.close()
