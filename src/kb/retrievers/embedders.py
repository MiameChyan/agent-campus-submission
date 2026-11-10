"""文本向量化。

HashEmbedder          离线哈希向量（jieba 词 + 字二元组哈希到固定维度）。不需要任何服务，结果确定，
                      **没有语义能力**，只用于在无密钥环境下跑通向量 / 混合检索的完整流程。
OpenAICompatEmbedder  OpenAI 兼容的 /embeddings 接口（默认硅基流动 BAAI/bge-m3），按内容哈希缓存到磁盘，
                      同一段文本只请求一次。
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path
from typing import Protocol

from .base import RetrieverError
from .bm25 import tokenize


class Embedder(Protocol):
    name: str
    dim: int | None

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


class HashEmbedder:
    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hash-{dim}"

    def _features(self, text: str) -> list[str]:
        chars = [c for c in text if not c.isspace()]
        return tokenize(text) + ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for f in self._features(text):
                h = int.from_bytes(hashlib.md5(f.encode("utf-8")).digest()[:8], "big")
                vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            out.append(_normalize(vec))
        return out


class OpenAICompatEmbedder:
    def __init__(self, base_url: str, api_key: str, model: str, cache_path: Path | None = None,
                 timeout: int = 30, batch_size: int = 32, client=None):
        if not api_key and client is None:
            raise RetrieverError("未配置 embedding 密钥（EMBEDDING_API_KEY 或 SILICONFLOW_API_KEY），"
                                 "可改用 EMBEDDING_PROVIDER=hash 离线运行。")
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)
        self.client, self.model, self.batch_size = client, model, batch_size
        self.name, self.dim = model, None
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, list[float]] = {}
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._cache = {}

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}\n{text}".encode("utf-8")).hexdigest()

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if self._key(t) not in self._cache]
        for i in range(0, len(missing), self.batch_size):
            batch = missing[i:i + self.batch_size]
            try:
                resp = self.client.embeddings.create(model=self.model, input=batch)
            except Exception as exc:  # 网络、鉴权、限流等
                raise RetrieverError(f"embedding 服务调用失败：{exc.__class__.__name__}: {exc}") from exc
            for text, item in zip(batch, resp.data):
                self._cache[self._key(text)] = _normalize(list(item.embedding))
        if missing and self.cache_path:
            with self._lock:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        vectors = [self._cache[self._key(t)] for t in texts]
        if vectors:
            self.dim = len(vectors[0])
        return vectors
