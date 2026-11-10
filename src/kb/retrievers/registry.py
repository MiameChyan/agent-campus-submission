"""按配置创建检索器。

RETRIEVER          bm25（默认）| vector | hybrid
EMBEDDING_PROVIDER openai_compat（默认，硅基流动 bge-m3）| hash（离线，无语义，只验证流程）
VECTOR_STORE       memory（默认）| milvus
"""
from __future__ import annotations

from ...config import ROOT, RetrievalSettings
from .base import Retriever, RetrieverError
from .bm25 import BM25Retriever
from .embedders import Embedder, HashEmbedder, OpenAICompatEmbedder
from .hybrid import HybridRetriever
from .vector import MemoryVectorStore, MilvusVectorStore, VectorRetriever, VectorStore

RETRIEVERS = ("bm25", "vector", "hybrid")


def create_embedder(s: RetrievalSettings) -> Embedder:
    if s.embedding_provider == "hash":
        return HashEmbedder()
    if s.embedding_provider == "openai_compat":
        return OpenAICompatEmbedder(s.embedding_base_url, s.embedding_api_key, s.embedding_model,
                                    cache_path=ROOT / ".cache" / "embeddings.json")
    raise RetrieverError(f"未知的 EMBEDDING_PROVIDER：{s.embedding_provider!r}（可选 openai_compat / hash）")


def create_store(s: RetrievalSettings) -> VectorStore:
    if s.vector_store == "memory":
        return MemoryVectorStore()
    if s.vector_store == "milvus":
        return MilvusVectorStore(s.milvus_uri, s.milvus_collection, s.milvus_token)
    raise RetrieverError(f"未知的 VECTOR_STORE：{s.vector_store!r}（可选 memory / milvus）")


def create_retriever(s: RetrievalSettings | None = None) -> Retriever:
    s = s or RetrievalSettings.from_env()
    if s.retriever == "bm25":
        return BM25Retriever()
    vector = VectorRetriever(create_embedder(s), create_store(s), min_score=s.vector_min_score)
    if s.retriever == "vector":
        return vector
    if s.retriever == "hybrid":
        return HybridRetriever([BM25Retriever(), vector], k=s.rrf_k)
    raise RetrieverError(f"未知的 RETRIEVER：{s.retriever!r}（可选 {', '.join(RETRIEVERS)}）")
