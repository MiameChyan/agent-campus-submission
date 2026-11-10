"""读取小节原文（L2）。只有读过的原文才能被引用（提交闸门会校验）。"""
from typing import Annotated

from src.tools.plugin import ToolContext, tool


@tool(description="读取小节原文（L2）及文档元数据。只有读过的小节原文才能被引用。")
def read_section(
    ctx: ToolContext,
    doc_id: Annotated[str, "文档 ID，如 D01"],
    section_id: Annotated[str, "小节 ID，如 s3"],
) -> dict:
    return ctx.kb.read_section(doc_id, section_id)
