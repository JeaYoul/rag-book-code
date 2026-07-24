#!/usr/bin/env python3
"""
reranker_with_fallback.py — 주력이 죽으면 예비가 이어받는다 (12장)

  주력: Qwen3-Reranker-8B (HTTP 서버, reranker_server.py)
  예비: bge-reranker-v2-m3 (로컬 CrossEncoder)

주력이 응답하지 않으면 예비가 대신 순위를 매긴다.
품질은 조금 낮아지지만 **시스템은 멈추지 않는다.**

  "실패를 없애려 하지 말고, 실패를 견디는 구조를 지어라." (2장)

사용:
    from reranker_with_fallback import RerankerWithFallback

    rr = RerankerWithFallback(
        primary_url="http://localhost:8090/v1/rerank",
        fallback_predict_fn=<예비_리랭커의_predict_함수>,   # 없으면 None
    )
    top = rr.rerank(query, docs, top_k=5)
"""
import logging
from typing import Callable, List, Optional, Sequence

import requests

log = logging.getLogger("reranker-fallback")


class RerankerWithFallback:
    def __init__(
        self,
        primary_url: str = "http://localhost:8090/v1/rerank",
        fallback_predict_fn: Optional[Callable[[Sequence], Sequence[float]]] = None,
        timeout: float = 30.0,
        max_docs: int = 64,
    ):
        """
        primary_url        : 주력 리랭커 서버 주소
        fallback_predict_fn: 예비 리랭커의 점수 함수.
                             (질문, 문서) 쌍 목록을 받아 점수 목록을 돌려주는 함수.
                             예) sentence_transformers CrossEncoder(...).predict
        max_docs           : 서버 상한과 맞춘다. 넘으면 잘라서 보낸다.
        """
        self.primary_url = primary_url
        self.fallback_predict_fn = fallback_predict_fn
        self.timeout = timeout
        self.max_docs = max_docs

    # ------------------------------------------------------------------
    def rerank(self, query: str, docs: List[dict], top_k: int = 5,
               text_key: str = "content") -> List[dict]:
        """docs: [{content: "...", ...}, ...] → 상위 top_k개를 rerank_score 붙여 반환"""
        if not docs:
            return []

        # 서버 상한을 넘지 않게 자른다 (앞쪽이 이미 벡터검색 상위이므로 앞을 남긴다)
        if len(docs) > self.max_docs:
            log.warning("문서 %d개 → 상한 %d개로 자름", len(docs), self.max_docs)
            docs = docs[: self.max_docs]

        texts = [d.get(text_key, "") for d in docs]

        scores = self._try_primary(query, texts)
        if scores is None:
            log.warning("주력 리랭커 실패 → 예비로 전환")
            scores = self._try_fallback(query, texts)

        if scores is None:
            # 둘 다 실패: 리랭킹 없이 원래 순서를 유지한다.
            # 못한 답이라도 나오는 게, 아무 답도 못 내는 것보다 낫다. (5장)
            log.error("리랭커 전부 실패 → 원본 순서 유지")
            return docs[:top_k]

        for d, s in zip(docs, scores):
            d["rerank_score"] = float(s)
        return sorted(docs, key=lambda x: x["rerank_score"], reverse=True)[:top_k]

    # ------------------------------------------------------------------
    def _try_primary(self, query: str, texts: List[str]) -> Optional[List[float]]:
        """주력 = HTTP 리랭커 서버."""
        try:
            r = requests.post(
                self.primary_url,
                json={"query": query, "documents": texts},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                log.warning("주력 응답 코드 %s: %s", r.status_code, r.text[:200])
                return None
            data = r.json()
            # 서버는 점수 내림차순으로 주므로, 원래 순서로 되돌린다
            scores = [0.0] * len(texts)
            for item in data.get("results", []):
                scores[item["index"]] = item["relevance_score"]
            return scores
        except Exception as e:
            log.warning("주력 호출 예외: %s", e)
            return None

    # ------------------------------------------------------------------
    def _try_fallback(self, query: str, texts: List[str]) -> Optional[List[float]]:
        """예비 = 로컬 CrossEncoder 등."""
        if self.fallback_predict_fn is None:
            return None
        try:
            pairs = [(query, t) for t in texts]
            return [float(s) for s in self.fallback_predict_fn(pairs)]
        except Exception as e:
            log.error("예비도 실패: %s", e)
            return None


# ---------------------------------------------------------------------------
# 예비 리랭커를 만드는 예 (선택)
# ---------------------------------------------------------------------------
def make_fallback(model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "cuda"):
    """sentence-transformers CrossEncoder로 예비 리랭커를 만든다."""
    from sentence_transformers import CrossEncoder
    ce = CrossEncoder(model_name, device=device, max_length=4096)
    return ce.predict


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    rr = RerankerWithFallback(
        primary_url="http://localhost:8090/v1/rerank",
        fallback_predict_fn=None,   # 예비를 쓰려면 make_fallback() 결과를 넣으세요
    )
    demo = [
        {"content": "설포라판은 Nrf2 경로를 활성화해 항산화 효소 발현을 높인다."},
        {"content": "담양은 대한민국 전라남도에 있는 지역이다."},
        {"content": "부티레이트와 설포라판은 모두 HDAC 억제 활성을 가진다."},
    ]
    for d in rr.rerank("설포라판과 부티레이트의 공통점은?", demo, top_k=3):
        print(f"{d.get('rerank_score', 0):.4f}  {d['content'][:40]}")
