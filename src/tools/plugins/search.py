"""知识库关键词 / 向量 / 混合检索（取决于 RETRIEVER 配置）。"""
from typing import Annotated

from src.tools.plugin import ToolContext, tool


@tool(description=(
    "检索知识库小节，返回 doc_id/section_id/版本/状态/短预览。检索方式由系统配置决定（默认 BM25 关键词，"
    "不理解同义词）。预览不能作为引用依据，需要用 read_section 读取原文。无命中或命中不相关时可换关键词再搜或改用 browse。"
))
def search(
    ctx: ToolContext,
    query: Annotated[str, "检索关键词，建议使用制度原文可能出现的词"],
    top_k: Annotated[int, "返回条数，1-8，常用 5"],
) -> dict:
    top_k = max(1, min(int(top_k), 8))
    hits = ctx.kb.search(query, top_k=top_k)
    return {
        "query": query,
        "retriever": ctx.kb.retriever.name,
        "hits": hits,
        "note": "" if hits else "无命中，可换关键词或用 browse 浏览目录",
    }
