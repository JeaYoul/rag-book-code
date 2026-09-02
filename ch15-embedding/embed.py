#!/usr/bin/env python3
"""
embed.py — 조각을 의미의 숫자로 (15장 "임베딩 · 대량 임베딩")

    python embed.py chunks/PMC000001.jsonl --out chunks/PMC000001.embedded.jsonl
    python embed.py chunks/*.jsonl --out-dir embedded/          # 여러 파일

12장의 임베딩 모델 BAAI/bge-m3 (1024차원). 규칙 셋:
    - 넣을 때와 찾을 때 같은 모델 (encode_query 도 여기서 가져다 쓴다)
    - normalize_embeddings=True — 길이를 1로, 코사인 유사도용
    - 배치 32 (ENCODE_BATCH) — 실제 시스템 값

--fake 를 주면 모델 없이 결정적 가짜 벡터를 만든다. 흐름을 실습·테스트할 때만 쓴다.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")
DIM = 1024
ENCODE_BATCH = 32


class Encoder:
    """싱글톤처럼 한 번만 로드해서 쓴다."""
    _model = None

    def __init__(self, fake: bool = False):
        self.fake = fake
        if not fake and Encoder._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"임베딩 모델 로딩: {MODEL_NAME} ({DEVICE})")
            Encoder._model = SentenceTransformer(MODEL_NAME, device=DEVICE)

    def encode(self, texts, batch_size=ENCODE_BATCH):
        if self.fake:
            return [self._fake_vector(t) for t in texts]
        vecs = Encoder._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,          # 길이를 1로 — 코사인 유사도용
            show_progress_bar=len(texts) > 10,
        )
        return [v.tolist() for v in vecs]

    def encode_query(self, query: str):
        """16장에서 질문을 벡터로 바꿀 때도 반드시 이 함수 — 같은 모델, 같은 정규화."""
        return self.encode([query])[0]

    @staticmethod
    def _fake_vector(text: str):
        """모델 없이 실습용 — 글자에서 결정적으로 만든 단위 벡터. 뜻은 없다."""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [((h[i % 32] * (i + 1)) % 251) / 251.0 - 0.5 for i in range(DIM)]
        norm = sum(x * x for x in raw) ** 0.5
        return [x / norm for x in raw]


def embed_file(enc: Encoder, src: Path, dst: Path) -> int:
    chunks = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [c["content"] for c in chunks]                 # 머리글이 붙은 임베딩용 글
    vecs = []
    for start in range(0, len(texts), ENCODE_BATCH):      # 32개씩
        vecs.extend(enc.encode(texts[start:start + ENCODE_BATCH]))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        for c, v in zip(chunks, vecs):
            assert len(v) == DIM, f"차원이 {DIM}이 아니다: {len(v)}"
            c["embedding"] = v
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return len(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, help="입력이 하나일 때 출력 파일")
    ap.add_argument("--out-dir", type=Path, help="입력이 여럿일 때 출력 폴더")
    ap.add_argument("--fake", action="store_true", help="모델 없이 가짜 벡터 (실습·테스트용)")
    a = ap.parse_args()
    if len(a.inputs) == 1 and a.out:
        pairs = [(a.inputs[0], a.out)]
    elif a.out_dir:
        pairs = [(p, a.out_dir / p.name.replace(".jsonl", ".embedded.jsonl")) for p in a.inputs]
    else:
        ap.error("--out (파일 하나) 또는 --out-dir (여러 파일) 을 주어라")

    enc = Encoder(fake=a.fake)
    total = 0
    for src, dst in pairs:
        n = embed_file(enc, src, dst)
        total += n
        print(f"{src.name}: {n}개 → {dst}")
    print(f"총 {total}개 조각, {DIM}차원{' (가짜)' if a.fake else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
