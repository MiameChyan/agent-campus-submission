"""向量检索：Embedder（文本→向量）+ VectorStore（存储与近邻搜索），两者都可替换。

MemoryVectorStore   进程内余弦相似度（向量已归一化，点积即余弦），零部署，默认使用。
MilvusVectorStore   Milvus（pymilvus MilvusClient），配置 VECTOR_STORE=milvus 与 MILVUS_URI 后启用。
"""
from __future__ import annotations

from typing import Protocol

from .base import RetrieverError
from .embedders import Embedder


class VectorStore(Protocol):
    name: str

    def reset(self, dim: int) -> None: ...

    def add(self, ids: list[str], vectors: list[list[float]]) -> None: ...

    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float]]: ...


class MemoryVectorStore:
    name = "memory"

    def __init__(self):
        self._ids: list[str] = []
        self._vecs: list[list[float]] = []

    def reset(self, dim: int) -> None:
        self._ids, self._vecs = [], []

    def add(self, ids: list[str], vectors: list[list[float]]) -> None:
        self._ids += ids
        self._vecs += vectors

    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        scored = [(i, sum(a * b for a, b in zip(vector, v))) for i, v in zip(self._ids, self._vecs)]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


class MilvusVectorStore:
    name = "milvus"

    def __init__(self, uri: str, collection: str, token: str = "", client=None):
        if client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise RetrieverError("使用 Milvus 需要安装 pymilvus：pip install pymilvus") from exc
            try:
                client = MilvusClient(uri=uri, token=token or None)
            except Exception as exc:
                raise RetrieverError(f"无法连接 Milvus（{uri}）：{exc}") from exc
        self.client, self.collection = client, collection

    def reset(self, dim: int) -> None:
        try:
            if self.client.has_collection(self.collection):
                self.client.drop_collection(self.collection)
            self.client.create_collection(
                collection_name=self.collection, dimension=dim, primary_field_name="id",
                id_type="string", max_length=64, vector_field_name="vector", metric_type="COSINE", auto_id=False,
            )
        except Exception as exc:
            raise RetrieverError(f"Milvus 建表失败：{exc}") from exc

    def add(self, ids: list[str], vectors: list[list[float]]) -> None:
        try:
            self.client.insert(self.collection, [{"id": i, "vector": v} for i, v in zip(ids, vectors)])
        except Exception as exc:
            raise RetrieverError(f"Milvus 写入失败：{exc}") from exc

    def search(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        try:
            res = self.client.search(self.collection, data=[vector], limit=top_k, output_fields=["id"])
        except Exception as exc:
            raise RetrieverError(f"Milvus 检索失败：{exc}") from exc
        return [(str(hit["id"]), float(hit["distance"])) for hit in res[0]]


class VectorRetriever:
    def __init__(self, embedder: Embedder, store: VectorStore, min_score: float = 0.0):
        self.embedder, self.store, self.min_score = embedder, store, min_score
        self.name = f"vector({embedder.name}@{store.name})"

    def index(self, items: list[tuple[str, str]]) -> None:
        if not items:
            return
        ids, texts = zip(*items)
        vectors = self.embedder.embed(list(texts))
        self.store.reset(len(vectors[0]))
        self.store.add(list(ids), vectors)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        if not query.strip():
            return []
        vec = self.embedder.embed([query])[0]
        return [(i, s) for i, s in self.store.search(vec, top_k) if s > self.min_score]
