"""Harness 主循环：模型选择动作 → 执行工具 → 观察结果 → 模型调整下一步或结束。

代码负责：组装上下文（含状态栏）、执行工具、故障注入、预算、重复调用提示、提交闸门、轨迹。
模型负责：每一步调用哪个工具、用什么参数、何时以何种状态结束。代码里没有“检索到冲突就…”之类的业务分支。
"""
from __future__ import annotations

import json
import time
from typing import Callable

from ..kb.store import KnowledgeBase
from ..llm.base import LLMClient, LLMError
from ..tools.base import ToolExecutionError
from ..tools.faults import FaultInjector
from ..tools.registry import build_tools, execute_business_tool
from .gate import check_finish
from .prompts import SYSTEM_PROMPT
from .state import EvidenceItem, RunState
from .status_bar import render_status_bar
from .trace import finalize_trace, summarize_observation

MAX_GATE_REJECTIONS = 2
EventCallback = Callable[[dict], None]


def _history_block(history: list[dict] | None) -> str:
    """对话历史以文本形式放入本轮 user 消息（避免伪造不含 reasoning_content 的 assistant 消息）。"""
    if not history:
        return ""
    lines = ["【对话历史】"]
    for h in history:
        lines.append(f"用户：{h.get('question', '')}")
        ans = h.get("answer", "")
        cites = h.get("citations") or []
        if cites:
            ans += "（依据：" + "，".join(f"{c.get('doc_id')}#{c.get('section_id')}" for c in cites) + "）"
        lines.append(f"助手：{ans}")
    return "\n".join(lines) + "\n\n"


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        kb: KnowledgeBase,
        max_llm_turns: int = 8,
        max_tool_calls: int = 12,
        faults: FaultInjector | None = None,
        on_event: EventCallback | None = None,
        kb_label: str = "data/kb",
    ):
        self.llm, self.kb = llm, kb
        self.max_llm_turns, self.max_tool_calls = max_llm_turns, max_tool_calls
        self.faults = faults or FaultInjector()
        self.on_event = on_event or (lambda e: None)
        self.kb_label = kb_label
        self.tools = build_tools(kb)
        self.tool_schemas = [t.schema() for t in self.tools.values()]

    # ------------------------------------------------------------------
    def run(self, question: str, history: list[dict] | None = None) -> dict:
        t0 = time.perf_counter()
        state = RunState(self.max_llm_turns, self.max_tool_calls)
        steps: list[dict] = []
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _history_block(history) + f"【当前问题】{question}"},
        ]
        outcome: dict | None = None

        def add_step(**kw) -> dict:
            step = {"step": len(steps) + 1, "turn": state.llm_turns, **kw}
            steps.append(step)
            self.on_event({"type": "step", "step": step})
            return step

        while outcome is None:
            # ---- 预算检查：轮数 ----
            if state.llm_turns >= state.max_llm_turns:
                outcome = self._incomplete("llm_turns_exhausted", state)
                add_step(action="(budget)", args={}, reason="", ok=False,
                         observation=f"模型调用轮数达到上限 {state.max_llm_turns}，以未完成状态结束")
                break

            # ---- 模型决策（状态栏作为临时消息追加在末尾，不写入 messages）----
            context = messages + [{"role": "user", "content": render_status_bar(state)}]
            try:
                resp = self.llm.chat(context, self.tool_schemas)
            except LLMError as exc:
                state.llm_turns += 1
                outcome = {"status": "model_error", "answer": "", "gaps": [f"模型调用失败：{exc}"]}
                add_step(action="(model_error)", args={}, reason="", ok=False, observation=str(exc)[:200])
                break
            state.llm_turns += 1
            for k, v in (resp.usage or {}).items():
                state.usage[k] += v
            messages.append(resp.assistant_message)

            if not resp.tool_calls:
                # 模型直接输出文本而没有调用工具：不当作最终答案（没有经过闸门），提醒其用 finish/ask_user 结束
                add_step(action="(text_without_tool)", args={}, reason="", ok=False,
                         observation=f"模型未调用工具，输出：{resp.content[:80]}")
                messages.append({"role": "user", "content": "请通过工具继续：需要资料就调用检索/读取工具；要结束请调用 finish 或 ask_user，直接输出的文本不会被采纳。"})
                continue

            for call in resp.tool_calls:
                obs, step_info = self._handle_call(call, state)
                if outcome is None and step_info.get("outcome"):
                    outcome = step_info.pop("outcome")
                else:
                    step_info.pop("outcome", None)
                add_step(**step_info)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(obs, ensure_ascii=False)})

            if outcome is None and state.gate_rejections > MAX_GATE_REJECTIONS:
                outcome = self._incomplete("gate_rejections_exhausted", state)
            if outcome is None and state.budget_blocked:
                outcome = self._incomplete("tool_calls_exhausted", state)

        result = self._build_result(question, outcome, state, steps, t0)
        self.on_event({"type": "final", "result": result})
        return result

    # ------------------------------------------------------------------
    def _handle_call(self, call, state: RunState) -> tuple[dict, dict]:
        name = call.name
        try:
            args = json.loads(call.arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("参数必须是 JSON 对象")
        except (json.JSONDecodeError, ValueError) as exc:
            obs = ToolExecutionError("InvalidArguments", f"参数不是合法 JSON：{exc}", False, "按工具定义重新生成参数。").to_observation()
            state.last_errors.append(f"{name}: 参数 JSON 无效")
            return obs, dict(action=name, args={"_raw": call.arguments[:200]}, reason="", ok=False,
                             observation=summarize_observation(name, obs), kind="error")
        reason = str(args.get("reason", ""))
        shown_args = {k: v for k, v in args.items() if k != "reason"}
        tool = self.tools.get(name)
        if tool is None:
            obs = ToolExecutionError("UnknownTool", f"不存在工具 {name}", False, f"可用工具：{list(self.tools)}").to_observation()
            return obs, dict(action=name, args=shown_args, reason=reason, ok=False, observation=obs["message"], kind="error")

        # ---- 终止工具 ----
        if name == "finish":
            gate = check_finish(args, state)
            if gate.ok:
                outcome = {
                    "status": args["status"],
                    "answer": args.get("answer", ""),
                    "citations": gate.citations,
                    "conflicts": args.get("conflicts") or [],
                    "gaps": args.get("gaps") or [],
                }
                obs = {"ok": True, "data": {"accepted": True}}
                return obs, dict(action="finish", args={"status": args.get("status")}, reason=reason, ok=True,
                                 observation=f"闸门通过，状态 {args.get('status')}，有效引用 {len(gate.citations)} 条",
                                 kind="terminal", outcome=outcome)
            state.gate_rejections += 1
            state.gate_feedback.append("；".join(gate.problems))
            obs = {"ok": False, "error_type": "GateRejected", "problems": gate.problems, "retryable": True,
                   "suggestion": "按问题修正后重新 finish；需要更多证据就先 read_section。"}
            return obs, dict(action="finish", args={"status": args.get("status")}, reason=reason, ok=False,
                             observation="闸门退回：" + "；".join(gate.problems)[:160], kind="gate_reject")
        if name == "ask_user":
            outcome = {"status": "need_clarification", "answer": "", "clarifying_question": args.get("question", "")}
            return {"ok": True, "data": {"asked": True}}, dict(
                action="ask_user", args=shown_args, reason=reason, ok=True,
                observation="向用户追问，本轮结束", kind="terminal", outcome=outcome)

        # ---- 控制工具 ----
        if name == "update_plan":
            state.plan = list(args.get("todos") or [])
            obs = {"ok": True, "data": {"todos": state.plan}}
            return obs, dict(action=name, args=shown_args, reason=reason, ok=True,
                             observation=summarize_observation(name, obs), kind="control")

        # ---- 业务工具（计入预算）----
        if state.tool_calls >= state.max_tool_calls:
            state.budget_blocked = True
            obs = ToolExecutionError("BudgetExhausted", f"业务工具调用已达上限 {state.max_tool_calls} 次",
                                     False, "请基于已读证据 finish，或 ask_user。").to_observation()
            return obs, dict(action=name, args=shown_args, reason=reason, ok=False,
                             observation=obs["message"], kind="budget")
        state.tool_calls += 1
        state.tool_counts[name] += 1
        sig = state.signature(name, args)
        t0 = time.perf_counter()
        try:
            data = execute_business_tool(tool, args, self.faults)
            obs = {"ok": True, "data": data}
            if sig in state.call_cache:
                obs["note"] = f"与第 {state.call_cache[sig]} 次调用参数完全相同，结果不会变化；请换关键词、换工具或结束。"
            else:
                state.call_cache[sig] = str(state.tool_calls)
            self._update_state(name, data, state)
        except ToolExecutionError as exc:
            obs = exc.to_observation()
            state.last_errors.append(f"{name} 第 {state.tool_counts[name]} 次调用失败：{exc.error_type}，"
                                     f"{'可重试' if exc.retryable else '不可重试'}。建议：{exc.suggestion}")
        elapsed = int((time.perf_counter() - t0) * 1000)
        observation = summarize_observation(name, obs) + (f"（{obs['note']}）" if obs.get("note") else "")
        return obs, dict(action=name, args=shown_args, reason=reason, ok=obs.get("ok", False),
                         observation=observation, kind="business", elapsed_ms=elapsed)

    @staticmethod
    def _update_state(name: str, data: dict, state: RunState) -> None:
        if name == "search":
            for h in data.get("hits", []):
                state.seen_docs.setdefault(h["doc_id"], {k: h[k] for k in ("doc_id", "title", "status", "version_date")})
        elif name == "browse":
            for d in data.get("documents", []):
                state.seen_docs.setdefault(d["doc_id"], {k: d[k] for k in ("doc_id", "title", "status", "version_date")})
        elif name == "outline":
            state.seen_docs[data["doc_id"]] = {k: data[k] for k in ("doc_id", "title", "status", "version_date")}
        elif name == "read_section":
            ref = f"{data['doc_id']}#{data['section_id']}"
            state.evidence[ref] = EvidenceItem(
                ref=ref, doc_id=data["doc_id"], section_id=data["section_id"], title=data["title"],
                section_title=data["section_title"], version_date=data["version_date"], status=data["status"],
                scope=data["scope"], supersedes=data["supersedes"], superseded_by=data["superseded_by"], text=data["text"],
            )
            state.seen_docs[data["doc_id"]] = {k: data[k] for k in ("doc_id", "title", "status", "version_date")}

    @staticmethod
    def _incomplete(reason: str, state: RunState) -> dict:
        read = [f"{e.ref}《{e.title}》{e.section_title}" for e in state.evidence.values()]
        return {
            "status": "incomplete",
            "incomplete_reason": reason,
            "answer": "",
            "gaps": ["达到执行上限，任务未完成；以下为已收集但未形成结论的证据：" + ("；".join(read) if read else "无")],
        }

    def _build_result(self, question: str, outcome: dict, state: RunState, steps: list[dict], t0: float) -> dict:
        return {
            "question": question,
            "status": outcome.get("status"),
            "incomplete_reason": outcome.get("incomplete_reason"),
            "mode": self.llm.mode,
            "model": self.llm.name,
            "kb": self.kb_label,
            "fault_injection": self.faults.describe() or None,
            "answer": outcome.get("answer", ""),
            "citations": outcome.get("citations", []),
            "conflicts": outcome.get("conflicts", []),
            "gaps": outcome.get("gaps", []),
            "clarifying_question": outcome.get("clarifying_question"),
            "stats": {
                "llm_turns": state.llm_turns,
                "tool_calls": state.tool_calls,
                "tool_calls_by_name": dict(state.tool_counts),
                "gate_rejections": state.gate_rejections,
                "budget": {"max_llm_turns": state.max_llm_turns, "max_tool_calls": state.max_tool_calls},
                "prompt_tokens": state.usage.get("prompt_tokens", 0),
                "completion_tokens": state.usage.get("completion_tokens", 0),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
            "trace": finalize_trace(steps),
        }
