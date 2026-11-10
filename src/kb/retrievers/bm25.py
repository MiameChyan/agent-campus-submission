"""jieba 分词 + BM25 关键词检索（无向量、无外部服务）。

选择 BM25 而不是向量检索的原因见 docs/02-solution.md：知识库规模小、难点在冲突与版本元数据，
且评审复现不应依赖 Milvus / embedding 密钥。实现 retrievers/base.py 中的 Retriever 协议。
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

import jieba

jieba.setLogLevel(logging.WARNING)
for _w in ("年假", "远程办公", "报销", "报销期限", "电子发票", "星剪", "水印", "自动字幕", "试用期", "工龄", "笔记本电脑"):
    jieba.add_word(_w)

_STOP = set("的 了 和 与 及 或 是 在 有 为 对 等 由 须 应 可 吗 呢 吧 啊 么 什么 多少 怎么 如何 哪些 是否 请问 我 我们 你 公司 一下 之 其 该 本".split())
_PUNCT = re.compile(r"^[\s\W_]+$", re.U)


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in jieba.lcut_for_search(text.lower()):
        tok = tok.strip()
        if not tok or tok in _STOP or _PUNCT.match(tok):
            continue
        tokens.append(tok)
    return tokens


class BM25Retriever:
    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self._ids: list[str] = []
        self._docs: list[Counter] = []
        self._lens: list[int] = []
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0

    def index(self, items: list[tuple[str, str]]) -> None:
        self._ids, self._docs, self._lens = [], [], []
        for item_id, text in items:
            self.add(item_id, text)
        self.build()

    def add(self, item_id: str, text: str) -> None:
        toks = tokenize(text)
        self._ids.append(item_id)
        self._docs.append(Counter(toks))
        self._lens.append(len(toks))

    def build(self) -> None:
        n = len(self._docs)
        df: Counter = Counter()
        for c in self._docs:
            df.update(c.keys())
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._avgdl = (sum(self._lens) / n) if n else 0.0

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q = tokenize(query)
        if not q or not self._docs:
            return []
        scored = []
        for i, c in enumerate(self._docs):
            s = 0.0
            for t in q:
                if t not in c:
                    continue
                tf = c[t]
                denom = tf + self.k1 * (1 - self.b + self.b * self._lens[i] / (self._avgdl or 1))
                s += self._idf.get(t, 0.0) * tf * (self.k1 + 1) / denom
            if s > 0:
                scored.append((self._ids[i], s))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]
