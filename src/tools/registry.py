"""工具注册：核心工具（计划、追问、提交）固定在代码中，业务工具来自插件目录（可热加载）。

核心工具与 harness 的结束逻辑、提交闸门绑定，因此不做成插件；业务工具（检索、浏览、读原文……）
只需要“输入参数 → 返回 JSON”，放在 src/tools/plugins/ 下即可扩展。
"""
from __future__ import annotations

from ..kb.retrievers import RetrieverError
from .base import Tool, ToolExecutionError
from .faults import FaultInjector
from .plugin import PluginRegistry, ToolContext, default_registry

FINISH_STATUSES = ["answered", "conflict_needs_confirmation", "out_of_scope", "tool_error"]

CORE_TOOLS = [
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


def build_tools(kb, plugins: PluginRegistry | None = None) -> dict[str, Tool]:
    """本次运行可用的全部工具：插件业务工具 + 核心工具（同名时报错，核心工具名为保留字）。"""
    plugins = plugins or default_registry()
    business = plugins.build(ToolContext(kb=kb))
    clash = set(business) & {t.name for t in CORE_TOOLS}
    if clash:
        raise ValueError(f"插件工具名与核心工具冲突：{sorted(clash)}")
    return {**business, **{t.name: t for t in CORE_TOOLS}}


def execute_business_tool(tool: Tool, args: dict, faults: FaultInjector | None):
    """执行业务工具；所有异常都转换为 ToolExecutionError，交给模型观察，不打断主循环。"""
    if faults:
        faults.check(tool.name)
    call_args = {k: v for k, v in args.items() if k in tool.properties}
    try:
        return tool.handler(**call_args)
    except ToolExecutionError:
        raise
    except RetrieverError as exc:
        raise ToolExecutionError("RetrieverUnavailable", str(exc), retryable=True,
                                 suggestion="可重试一次；或改用 browse / outline 按目录查找。") from exc
    except KeyError as exc:
        raise ToolExecutionError("NotFound", str(exc.args[0] if exc.args else exc), retryable=False,
                                 suggestion="检查 doc_id/section_id/path 是否来自之前的检索或浏览结果。") from exc
    except TypeError as exc:
        raise ToolExecutionError("InvalidArguments", f"参数错误：{exc}", retryable=False,
                                 suggestion="按工具定义补全参数后再调用。") from exc
    except Exception as exc:  # 插件内部的其他错误
        raise ToolExecutionError("PluginError", f"{tool.name} 执行出错：{exc.__class__.__name__}: {exc}",
                                 retryable=False, suggestion="换用其他工具，或以 tool_error 结束并说明。") from exc
