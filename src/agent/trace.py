"""运行轨迹：每一步记录动作、参数、返回摘要、决策依据，结束后补上“后续动作”。不含模型内部思维。"""
from __future__ import annotations

import json


def _short(text: str, n: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "…"


def summarize_observation(tool: str, obs: dict) -> str:
    if not obs.get("ok", True):
        return f"失败 {obs.get('error_type')}（{'可重试' if obs.get('retryable') else '不可重试'}）：{_short(obs.get('message', ''), 80)}"
    data = obs.get("data", obs)
    if tool == "search":
        hits = data.get("hits", [])
        if not hits:
            return f"“{data.get('query')}” 无命中"
        return f"“{data.get('query')}” 命中 {len(hits)} 条：" + "；".join(
            f"{h['doc_id']}#{h['section_id']} {h['section_title']}({h['status']})" for h in hits[:4]
        )
    if tool == "browse":
        subs = "、".join(s["path"] for s in data.get("subdirs", [])) or "无"
        docs = "、".join(f"{d['doc_id']}({d['status']})" for d in data.get("documents", [])) or "无"
        return f"目录 {data.get('path')}：子目录 {subs}；文档 {docs}"
    if tool == "outline":
        rel = []
        if data.get("supersedes"):
            rel.append("替代 " + ",".join(data["supersedes"]))
        if data.get("superseded_by"):
            rel.append("被 " + data["superseded_by"] + " 替代")
        return (f"{data.get('doc_id')}《{data.get('title')}》{data.get('status')} {data.get('version_date')} "
                f"范围:{data.get('scope')} {' '.join(rel)} 小节 {len(data.get('sections', []))} 个")
    if tool == "read_section":
        return f"{data.get('doc_id')}#{data.get('section_id')}（{data.get('status')}）{data.get('section_title')}：{_short(data.get('text', ''), 50)}"
    if tool == "update_plan":
        return f"计划 {len(data.get('todos', []))} 项"
    return _short(json.dumps(data, ensure_ascii=False), 80)


def finalize_trace(steps: list[dict]) -> list[dict]:
    for i, s in enumerate(steps):
        s["next_action"] = steps[i + 1]["action"] if i + 1 < len(steps) else "（结束）"
    return steps


def render_markdown(result: dict) -> str:
    lines = [
        f"# Trace：{result.get('question', '')}",
        "",
        f"- 模式：`{result.get('mode')}`　模型：`{result.get('model')}`　知识库：`{result.get('kb')}`"
        + (f"　故障注入：`{result['fault_injection']}`" if result.get("fault_injection") else ""),
        f"- 最终状态：**{result.get('status')}**" + (f"（{result.get('incomplete_reason')}）" if result.get("incomplete_reason") else ""),
        f"- 统计：模型调用 {result['stats']['llm_turns']} 轮，业务工具 {result['stats']['tool_calls']} 次，"
        f"闸门退回 {result['stats']['gate_rejections']} 次，耗时 {result['stats']['elapsed_ms']} ms",
        "",
        "| # | 轮 | 动作 | 参数 | 返回摘要 | 决策依据（模型给出） | 后续动作 |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in result.get("trace", []):
        args = json.dumps(s.get("args", {}), ensure_ascii=False)
        cells = [str(s.get("step")), str(s.get("turn")), s.get("action", ""), args, s.get("observation", ""),
                 s.get("reason", ""), s.get("next_action", "")]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", "## 最终输出", "", "```json",
              json.dumps({k: result.get(k) for k in ("status", "answer", "citations", "conflicts", "gaps", "clarifying_question")},
                         ensure_ascii=False, indent=2),
              "```", ""]
    return "\n".join(lines)
