"""工具注册表：业务工具（知识库四件套）+ 控制工具（计划）+ 终止工具（追问/结束）。"""
from __future__ import annotations

from ..kb.store import KnowledgeBase
from .base import Tool, ToolExecutionError
from .faults import FaultInjector

FINISH_STATUSES = ["answered", "conflict_needs_confirmation", "out_of_scope", "tool_error"]


def build_tools(kb: KnowledgeBase) -> dict[str, Tool]:
    def browse(path: str):
        return kb.browse(path)

    def outline(doc_id: str):
        return kb.outline(doc_id)

    def read_section(doc_id: str, section_id: str):
        return kb.read_section(doc_id, section_id)

    def search(query: str, top_k: int):
        top_k = max(1, min(int(top_k), 8))
        hits = kb.search(query, top_k=top_k)
        return {"query": query, "hits": hits, "note": "无命中，可换关键词或用 browse 浏览目录" if not hits else ""}

    tools = [
        Tool(
            name="search",
            kind="business",
            handler=search,
            description=(
                "关键词检索知识库小节（jieba+BM25，不理解同义词）。返回 doc_id/section_id/版本/状态/短预览。"
                "预览不能作为引用依据，需要用 read_section 读取原文。无命中或命中不相关时可换关键词再搜或改用 browse。"
            ),
            properties={
                "query": {"type": "string", "description": "检索关键词，建议使用制度原文可能出现的词"},
                "top_k": {"type": "integer", "description": "返回条数，1-8，常用 5"},
            },
        ),
        Tool(
            name="browse",
            kind="business",
            handler=browse,
            description="浏览知识库目录（L0）：列出子目录和文档的一句话摘要、版本日期、状态。path 用 '' 表示根目录，如 '制度/人事'。",
            properties={"path": {"type": "string", "description": "目录路径，根目录传空字符串"}},
        ),
        Tool(
            name="outline",
            kind="business",
            handler=outline,
            description="查看文档大纲（L1）：版本日期、状态、适用范围、替代关系（supersedes/superseded_by）、相关链接、小节列表。用于查证冲突与版本。",
            properties={"doc_id": {"type": "string", "description": "文档 ID，如 D01"}},
        ),
        Tool(
            name="read_section",
            kind="business",
            handler=read_section,
            description="读取小节原文（L2）及文档元数据。只有读过的小节原文才能被引用。",
            properties={
                "doc_id": {"type": "string", "description": "文档 ID，如 D01"},
                "section_id": {"type": "string", "description": "小节 ID，如 s3"},
            },
        ),
        Tool(
            name="update_plan",
            kind="control",
            description="写下/更新你的检索计划（多步问题时使用）。计划会显示在状态栏，不消耗业务工具预算。",
            properties={
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
                        },
                        "required": ["content", "status"],
                        "additionalProperties": False,
                    },
                }
            },
        ),
        Tool(
            name="ask_user",
            kind="terminal",
            description="向用户追问并结束本轮（问题缺少关键信息、无法确定指代，或需要用户确认适用制度时）。",
            properties={"question": {"type": "string", "description": "要问用户的问题"}},
        ),
        Tool(
            name="finish",
            kind="terminal",
            description=(
                "提交最终结果并结束。系统会校验引用：quote 必须是你用 read_section 读过的小节原文中的连续片段。"
                "status：answered=有依据的明确答案；conflict_needs_confirmation=资料冲突且无法查证优先级，需用户确认；"
                "out_of_scope=知识库无相关资料；tool_error=工具故障导致无法完成。"
            ),
            properties={
                "status": {"type": "string", "enum": FINISH_STATUSES},
                "answer": {"type": "string", "description": "给用户的回答；冲突时说明各方说法与需要确认的点，不得自行选边"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string"},
                            "section_id": {"type": "string"},
                            "quote": {"type": "string", "description": "原文中的连续片段，逐字复制"},
                        },
                        "required": ["doc_id", "section_id", "quote"],
                        "additionalProperties": False,
                    },
                },
                "conflicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "doc_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["description", "doc_ids"],
                        "additionalProperties": False,
                    },
                },
                "gaps": {"type": "array", "items": {"type": "string"}, "description": "资料缺口/未能确认的信息"},
            },
        ),
    ]
    return {t.name: t for t in tools}


def execute_business_tool(tool: Tool, args: dict, faults: FaultInjector | None):
    """执行业务工具；所有异常都转换为 ToolExecutionError，交给模型观察。"""
    if faults:
        faults.check(tool.name)
    call_args = {k: v for k, v in args.items() if k in tool.properties}
    try:
        return tool.handler(**call_args)
    except KeyError as exc:
        raise ToolExecutionError(
            "NotFound", str(exc.args[0] if exc.args else exc), retryable=False,
            suggestion="检查 doc_id/section_id/path 是否来自之前的检索或浏览结果。",
        ) from exc
    except TypeError as exc:
        raise ToolExecutionError(
            "InvalidArguments", f"参数错误：{exc}", retryable=False,
            suggestion="按工具定义补全参数后再调用。",
        ) from exc
