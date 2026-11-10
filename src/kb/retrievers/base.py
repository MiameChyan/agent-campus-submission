"""检索器接口：知识库只依赖这里的协议，具体实现（BM25 / 向量 / 混合）可通过配置切换。

    index(items)            建索引，items 为 [(小节 ID, 带上下文前缀的文本)]
    search(query, top_k)    返回 [(小节 ID, 分数)]，按分数从高到低

新增一种检索方式：实现这两个方法，并在 registry.py 的 create_retriever 中注册即可。
"""
from __future__ import annotations

from typing import Protocol


class Retriever(Protocol):
    name: str

    def index(self, items: list[tuple[str, str]]) -> None: ...

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]: ...


class RetrieverError(RuntimeError):
    """检索后端不可用（如 embedding 服务失败、Milvus 连接失败）。工具层会把它转成可重试的观察结果。"""
