"""状态栏（System Hint）：每轮调用模型前，把动态状态作为一条临时 user 消息追加在上下文末尾。

它不写入对话历史（下一轮重新生成），因此不会随轮数累积；模型每轮都能看到最新的预算、
计划、证据台账和错误详情。设计来源：《深入理解 AI Agent》第 2 章 system-hint 实验。
"""
from __future__ import annotations

from .prompts import STATUS_BAR_HEADER
from .state import RunState

_PLAN_MARK = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]"}


def render_status_bar(state: RunState) -> str:
    lines = [STATUS_BAR_HEADER, f"当前日期：{state.today}"]
    counts = "，".join(f"{k}×{v}" for k, v in sorted(state.tool_counts.items())) or "无"
    lines.append(
        f"预算：本次是第 {state.llm_turns + 1}/{state.max_llm_turns} 轮模型调用；"
        f"业务工具已用 {state.tool_calls}/{state.max_tool_calls} 次（{counts}）"
    )
    if state.turns_left <= 2 or state.tool_budget_left <= 2:
        lines.append("⚠ 预算即将耗尽：请优先基于已读证据 finish，或 ask_user；预算用完将以“未完成”结束。")

    if state.plan:
        lines.append("计划：")
        lines += [f"  {_PLAN_MARK.get(t.get('status'), '[ ]')} {t.get('content', '')}" for t in state.plan]

    if state.evidence:
        lines.append("证据台账（已读原文，可引用）：")
        for e in state.evidence.values():
            rel = []
            if e.supersedes:
                rel.append(f"替代 {','.join(e.supersedes)}")
            if e.superseded_by:
                rel.append(f"已被 {e.superseded_by} 替代")
            lines.append(
                f"  - {e.ref}《{e.title}》{e.section_title}｜版本 {e.version_date}｜{e.status}｜范围：{e.scope}"
                + (f"｜{'；'.join(rel)}" if rel else "")
            )
    else:
        lines.append("证据台账：尚未读取任何原文（finish 前需要 read_section）。")

    unread = [d for d in state.seen_docs.values() if not any(e.doc_id == d["doc_id"] for e in state.evidence.values())]
    if unread:
        lines.append("已发现但未读原文的文档：" + "，".join(
            f"{d['doc_id']}《{d.get('title', '')}》({d.get('status', '?')}, {d.get('version_date', '?')})" for d in unread
        ))

    if state.last_errors:
        lines.append("最近的工具错误：")
        lines += [f"  - {e}" for e in state.last_errors[-3:]]
    if state.gate_feedback:
        lines.append(f"提交闸门退回 {state.gate_rejections} 次，原因：")
        lines += [f"  - {f}" for f in state.gate_feedback[-1:]]
    return "\n".join(lines)
