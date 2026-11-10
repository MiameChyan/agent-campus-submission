"""混合检索：多个检索器的结果用 RRF（Reciprocal Rank Fusion）融合。

RRF 只看排名不看原始分数，因此 BM25 分数与余弦相似度量纲不同也能直接融合：
    score(d) = Σ 1 / (k + rank_i(d))
"""
from __future__ import annotations

from .base import Retriever


class HybridRetriever:
    def __init__(self, retrievers: list[Retriever], k: int = 60, depth: int = 20):
        self.retrievers, self.k, self.depth = retrievers, k, depth
        self.name = "hybrid(" + "+".join(r.name for r in retrievers) + ")"

    def index(self, items: list[tuple[str, str]]) -> None:
        for r in self.retrievers:
            r.index(items)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        fused: dict[str, float] = {}
        for r in self.retrievers:
            for rank, (item_id, _) in enumerate(r.search(query, top_k=max(top_k, self.depth)), 1):
                fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (self.k + rank)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        return [(i, round(s * 100, 4)) for i, s in ranked[:top_k]]   # ×100 只为便于阅读
