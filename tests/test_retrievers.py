"""可插拔检索：BM25 / 向量（内存、Milvus）/ 混合，以及检索后端故障的处理。"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.config import DEFAULT_KB, RetrievalSettings
from src.kb.retrievers import (
    BM25Retriever, HybridRetriever, MilvusVectorStore, RetrieverError, VectorRetriever, create_retriever,
)
from src.kb.retrievers.embedders import HashEmbedder, OpenAICompatEmbedder
from src.kb.retrievers.vector import MemoryVectorStore
from src.kb.store import KnowledgeBase


def _settings(**kw):
    return replace(RetrievalSettings.from_env(), embedding_provider="hash", **kw)


@pytest.mark.parametrize("mode,name", [
    ("bm25", "bm25"),
    ("vector", "vector(hash-512@memory)"),
    ("hybrid", "hybrid(bm25+vector(hash-512@memory))"),
])
def test_switch_retriever_by_config(mode, name):
    kb = KnowledgeBase.load(DEFAULT_KB, retriever=create_retriever(_settings(retriever=mode)))
    assert kb.retriever.name == name and kb.summary()["retriever"] == name
    assert kb.search("报销期限", 3)[0]["doc_id"] == "D01"


def test_unknown_options_raise():
    for kw in ({"retriever": "magic"}, {"retriever": "vector", "vector_store": "redis"}):
        with pytest.raises(RetrieverError):
            create_retriever(_settings(**kw))


def test_rrf_fuses_by_rank():
    class Fixed:
        def __init__(self, name, ranking):
            self.name, self.ranking = name, ranking

        def index(self, items):
            pass

        def search(self, query, top_k=5):
            return [(i, 100 - n) for n, i in enumerate(self.ranking)][:top_k]

    h = HybridRetriever([Fixed("a", ["x", "y", "z"]), Fixed("b", ["y", "z", "x"])], k=60)
    ids = [i for i, _ in h.search("q", 3)]
    assert ids[0] == "y"          # 两路都排得靠前
    assert set(ids) == {"x", "y", "z"}


def test_hash_embedder_is_deterministic_and_normalized():
    e = HashEmbedder(dim=64)
    a, b = e.embed(["报销期限 30 天"])[0], e.embed(["报销期限 30 天"])[0]
    assert a == b and abs(sum(v * v for v in a) - 1) < 1e-9


class FakeEmbeddingClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input):
        if self.fail:
            raise ConnectionError("network down")
        self.calls.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t)), 1.0, 0.0]) for t in input])


def test_openai_embedder_caches_to_disk(tmp_path):
    cache = tmp_path / "emb.json"
    client = FakeEmbeddingClient()
    e = OpenAICompatEmbedder("http://x", "k", "bge-m3", cache_path=cache, client=client)
    e.embed(["甲", "乙"])
    e.embed(["甲", "乙", "丙"])
    assert client.calls == [["甲", "乙"], ["丙"]]     # 已缓存的不再请求
    e2 = OpenAICompatEmbedder("http://x", "k", "bge-m3", cache_path=cache, client=FakeEmbeddingClient(fail=True))
    assert len(e2.embed(["甲"])[0]) == 3                # 从磁盘缓存读取，不触发网络


def test_openai_embedder_errors_become_retriever_error():
    e = OpenAICompatEmbedder("http://x", "k", "m", client=FakeEmbeddingClient(fail=True))
    with pytest.raises(RetrieverError):
        e.embed(["x"])
    with pytest.raises(RetrieverError):
        OpenAICompatEmbedder("http://x", "", "m")      # 没有密钥


class FakeMilvus:
    def __init__(self):
        self.rows, self.created, self.dropped = {}, [], []

    def has_collection(self, name):
        return name in self.created

    def drop_collection(self, name):
        self.dropped.append(name)

    def create_collection(self, **kw):
        self.created.append(kw["collection_name"])
        assert kw["metric_type"] == "COSINE" and kw["dimension"] == 512

    def insert(self, name, rows):
        self.rows.update({r["id"]: r["vector"] for r in rows})

    def search(self, name, data, limit, output_fields):
        q = data[0]
        scored = sorted(((i, sum(a * b for a, b in zip(q, v))) for i, v in self.rows.items()), key=lambda x: -x[1])
        return [[{"id": i, "distance": s} for i, s in scored[:limit]]]


def test_milvus_store_adapter():
    fake = FakeMilvus()
    retriever = VectorRetriever(HashEmbedder(), MilvusVectorStore("http://x", "c", client=fake))
    kb = KnowledgeBase.load(DEFAULT_KB, retriever=retriever)
    assert retriever.name == "vector(hash-512@milvus)" and len(fake.rows) == len(kb.sections)
    assert kb.search("报销期限", 1)[0]["doc_id"] == "D01"
    KnowledgeBase.load(DEFAULT_KB, retriever=retriever)    # 重建索引会先删表
    assert fake.dropped == ["c"]


def test_milvus_errors_become_retriever_error():
    class Broken(FakeMilvus):
        def search(self, *a, **k):
            raise RuntimeError("milvus down")

    store = MilvusVectorStore("http://x", "c", client=Broken())
    store.reset(512)
    with pytest.raises(RetrieverError):
        store.search([0.0] * 512, 3)


def test_retriever_failure_is_observed_by_model(make_agent, kb):
    """检索后端故障 → 工具返回可重试的 RetrieverUnavailable，由模型决定改用目录浏览。"""
    import json

    from src.llm.mock import ScriptedLLM

    class Down(BM25Retriever):
        def search(self, query, top_k=5):
            raise RetrieverError("embedding 服务调用失败：timeout")

    broken_kb = KnowledgeBase.load(DEFAULT_KB, retriever=Down())
    R = {"reason": "t"}
    llm = ScriptedLLM([[("search", {"query": "远程办公", "top_k": 3, **R})],
                       [("ask_user", {"question": "?", **R})]])
    make_agent(llm, knowledge=broken_kb).run("q")
    obs = json.loads([m for m in llm.contexts[1] if m["role"] == "tool"][-1]["content"])
    assert obs["error_type"] == "RetrieverUnavailable" and obs["retryable"] is True


def test_memory_store_ranks_by_cosine():
    s = MemoryVectorStore()
    s.add(["a", "b"], [[1.0, 0.0], [0.0, 1.0]])
    assert s.search([0.9, 0.1], 1)[0][0] == "a"
