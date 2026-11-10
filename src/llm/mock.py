"""离线替身模型。

MockLLM（--mock）：按固定规则读取上下文中的工具结果来选择下一步，用于无密钥时跑通流程、
    生成离线 trace、做端到端测试。**它是预设规则，不是模型决策，只能证明 harness 流程、
    工具、闸门、预算与 trace 正常，不能证明真实模型的决策效果。** 已知局限：不理解改写问题与
    上下文追问，不会查证适用范围。
ScriptedLLM：按给定脚本逐轮返回工具调用，供单元测试精确控制每一步。
"""
from __future__ import annotations

import itertools
import json
import re

from .base import LLMResponse, ToolCall

_ids = itertools.count(1)


def _call(name: str, **args) -> ToolCall:
    return ToolCall(id=f"call_{next(_ids)}", name=name, arguments=json.dumps(args, ensure_ascii=False))


def make_response(calls: list[ToolCall], content: str = "") -> LLMResponse:
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in calls]
    return LLMResponse(content=content, tool_calls=calls, assistant_message=msg, usage={})


def _history(messages: list[dict]) -> list[tuple[str, dict, dict]]:
    """从上下文还原 (工具名, 参数, 观察) 序列。"""
    pending: dict[str, tuple[str, dict]] = {}
    out = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                pending[tc["id"]] = (tc["function"]["name"], json.loads(tc["function"]["arguments"] or "{}"))
        elif m.get("role") == "tool" and m.get("tool_call_id") in pending:
            name, args = pending.pop(m["tool_call_id"])
            out.append((name, args, json.loads(m["content"])))
    return out


def _question(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user" and "【当前问题】" in (m.get("content") or ""):
            return m["content"].split("【当前问题】", 1)[1].strip()
    return ""


def _first_sentence(text: str) -> str:
    return re.split(r"[。；]", text.strip())[0]


class MockLLM:
    name = "mock-policy"
    mode = "offline_mock"

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        q = _question(messages)
        hist = _history(messages)
        failed_search = [h for h in hist if h[0] == "search" and not h[2].get("ok")]
        ok_search = [h for h in hist if h[0] == "search" and h[2].get("ok")]
        reads = {f"{h[2]['data']['doc_id']}#{h[2]['data']['section_id']}": h[2]["data"]
                 for h in hist if h[0] == "read_section" and h[2].get("ok")}

        # 1) 检索：失败可重试一次，连续失败两次则以 tool_error 结束
        if not ok_search:
            if len(failed_search) >= 2:
                return make_response([_call("finish", status="tool_error", answer="检索服务连续失败，暂时无法回答该问题，请稍后重试。",
                                            citations=[], conflicts=[], gaps=["search 工具连续两次失败"],
                                            reason="[mock] 检索连续失败两次，停止并报告")])
            reason = "[mock] 检索失败一次，按建议重试" if failed_search else "[mock] 先用问题原文检索"
            return make_response([_call("search", query=q, top_k=5, reason=reason)])

        hits = ok_search[-1][2]["data"]["hits"]
        if not hits:
            return make_response([_call("finish", status="out_of_scope", answer="知识库中没有找到与该问题相关的资料，无法回答。",
                                        citations=[], conflicts=[], gaps=[f"知识库未覆盖：{q}"],
                                        reason="[mock] 检索无命中，判定为资料外问题")])

        # 2) 读原文：读取得分不低于最高分一半、来自不同文档的前两条（跳过已废止文档）
        top = hits[0]["score"]
        wanted, seen_docs = [], set()
        for h in hits:
            if h["status"] == "已废止" or h["doc_id"] in seen_docs or h["score"] < top * 0.5:
                continue
            seen_docs.add(h["doc_id"])
            wanted.append(h)
            if len(wanted) == 2:
                break
        to_read = [h for h in wanted if f"{h['doc_id']}#{h['section_id']}" not in reads]
        if to_read:
            return make_response([_call("read_section", doc_id=h["doc_id"], section_id=h["section_id"],
                                        reason="[mock] 读取高分命中的原文") for h in to_read])

        # 3) 结束：两份现行文档给出不同“N 天”数值 → 冲突；否则按第一条原文回答
        current = [d for d in reads.values() if d["status"] == "现行"]
        days = {d["doc_id"]: re.findall(r"(\d+)\s*天", d["text"]) for d in current}
        with_days = [d for d in current if days[d["doc_id"]]]
        if len(with_days) >= 2 and len({tuple(days[d["doc_id"]]) for d in with_days}) >= 2:
            a, b = with_days[:2]
            return make_response([_call(
                "finish", status="conflict_needs_confirmation",
                answer=f"资料存在冲突：{a['doc_id']} 与 {b['doc_id']} 的规定不一致，请确认适用哪份制度。",
                citations=[{"doc_id": d["doc_id"], "section_id": d["section_id"], "quote": _first_sentence(d["text"])} for d in (a, b)],
                conflicts=[{"description": "两份现行文档给出的天数不同", "doc_ids": [a["doc_id"], b["doc_id"]]}],
                gaps=["未找到两份文档的优先级或适用范围说明"],
                reason="[mock] 两份现行文档数值不同，列出冲突")])
        d = current[0] if current else next(iter(reads.values()))
        return make_response([_call(
            "finish", status="answered", answer=_first_sentence(d["text"]) + "。",
            citations=[{"doc_id": d["doc_id"], "section_id": d["section_id"], "quote": _first_sentence(d["text"])}],
            conflicts=[], gaps=[], reason="[mock] 依据已读原文回答")])


class ScriptedLLM:
    """按脚本逐轮返回；脚本元素是 [(tool_name, args), ...]、LLMResponse 或 Exception。"""

    name = "scripted"
    mode = "scripted"

    def __init__(self, script: list):
        self.script = list(script)
        self.contexts: list[list[dict]] = []   # 记录每轮收到的上下文，便于断言

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.contexts.append([dict(m) for m in messages])
        if not self.script:
            raise AssertionError("ScriptedLLM 脚本已用完")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return make_response([_call(name, **args) for name, args in item])
