"""按目录浏览知识库（L0）。"""
from typing import Annotated

from src.tools.plugin import ToolContext, tool


@tool(description="浏览知识库目录（L0）：列出子目录和文档的一句话摘要、版本日期、状态。path 用 '' 表示根目录，如 '制度/人事'。")
def browse(ctx: ToolContext, path: Annotated[str, "目录路径，根目录传空字符串"]) -> dict:
    return ctx.kb.browse(path)
