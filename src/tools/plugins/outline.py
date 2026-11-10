"""查看文档大纲与元数据（L1），用于查证版本、适用范围与替代关系。"""
from typing import Annotated

from src.tools.plugin import ToolContext, tool


@tool(description="查看文档大纲（L1）：版本日期、状态、适用范围、替代关系（supersedes/superseded_by）、相关链接、小节列表。用于查证冲突与版本。")
def outline(ctx: ToolContext, doc_id: Annotated[str, "文档 ID，如 D01"]) -> dict:
    return ctx.kb.outline(doc_id)
