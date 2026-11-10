"""Harness 循环机制（ScriptedLLM 精确控制每一轮的动作）。"""
import json

from src.agent.prompts import STATUS_BAR_HEADER
from src.llm.base import LLMError
from src.llm.mock import ScriptedLLM, make_response

R = {"reason": "测试"}


def _finish(status, citations, **kw):
    return ("finish", {"status": status, "answer": kw.get("answer", "回答"), "citations": citations,
                       "conflicts": kw.get("conflicts", []), "gaps": kw.get("gaps", []), **R})


CITE_D05 = [{"doc_id": "D05", "section_id": "s2", "quote": "员工每周最多可远程办公 2 天"}]


def test_normal_loop_search_read_finish(make_agent):
    llm = ScriptedLLM([
        [("search", {"query": "远程办公 天数", "top_k": 3, **R})],
        [("read_section", {"doc_id": "D05", "section_id": "s2", **R})],
        [_finish("answered", CITE_D05)],
    ])
    res = make_agent(llm).run("每周可以远程办公几天？")
    assert res["status"] == "answered"
    assert [s["action"] for s in res["trace"]] == ["search", "read_section", "finish"]
    assert res["trace"][0]["next_action"] == "read_section" and res["trace"][-1]["next_action"] == "（结束）"
    assert res["citations"][0]["doc_status"] == "现行"
    assert res["stats"] == {**res["stats"], "llm_turns": 3, "tool_calls": 2}


def test_status_bar_is_temporary_and_up_to_date(make_agent):
    llm = ScriptedLLM([
        [("read_section", {"doc_id": "D05", "section_id": "s2", **R})],
        [_finish("answered", CITE_D05)],
    ])
    make_agent(llm).run("q")
    first, second = llm.contexts
    assert first[-1]["content"].startswith(STATUS_BAR_HEADER) and "尚未读取任何原文" in first[-1]["content"]
    assert "D05#s2" in second[-1]["content"] and "业务工具已用 1/12" in second[-1]["content"]
    # 上一轮的状态栏不会留在历史中
    assert sum(STATUS_BAR_HEADER in (m.get("content") or "") for m in second) == 1


def test_gate_rejection_is_fed_back_and_model_can_fix(make_agent):
    bad = [{"doc_id": "D05", "section_id": "s2", "quote": "每周可以远程两天"}]
    llm = ScriptedLLM([
        [("read_section", {"doc_id": "D05", "section_id": "s2", **R})],
        [_finish("answered", bad)],
        [_finish("answered", CITE_D05)],
    ])
    res = make_agent(llm).run("q")
    assert res["status"] == "answered" and res["stats"]["gate_rejections"] == 1
    tool_msgs = [m for m in llm.contexts[2] if m["role"] == "tool"]
    assert json.loads(tool_msgs[-1]["content"])["error_type"] == "GateRejected"


def test_tool_failure_is_observed_not_auto_retried(make_agent):
    llm = ScriptedLLM([
        [("search", {"query": "远程办公", "top_k": 3, **R})],
        [("browse", {"path": "制度/人事", **R})],          # 模型自己决定改用目录浏览
        [("read_section", {"doc_id": "D05", "section_id": "s2", **R})],
        [_finish("answered", CITE_D05)],
    ])
    res = make_agent(llm, fail="search:always").run("q")
    assert res["status"] == "answered"
    assert res["stats"]["tool_calls_by_name"]["search"] == 1        # 代码没有自动重试
    obs = json.loads([m for m in llm.contexts[1] if m["role"] == "tool"][-1]["content"])
    assert obs["ok"] is False and obs["retryable"] is True and obs["suggestion"]
    assert "最近的工具错误" in llm.contexts[1][-1]["content"]


def test_llm_turn_budget_returns_incomplete(make_agent):
    llm = ScriptedLLM([[("search", {"query": f"报销{i}", "top_k": 3, **R})] for i in range(5)])
    res = make_agent(llm, max_llm_turns=3).run("q")
    assert res["status"] == "incomplete" and res["incomplete_reason"] == "llm_turns_exhausted"
    assert res["answer"] == "" and res["stats"]["llm_turns"] == 3


def test_tool_call_budget_returns_incomplete(make_agent):
    llm = ScriptedLLM([[("search", {"query": f"报销{i}", "top_k": 3, **R})] for i in range(5)])
    res = make_agent(llm, max_tool_calls=2).run("q")
    assert res["status"] == "incomplete" and res["incomplete_reason"] == "tool_calls_exhausted"
    assert res["stats"]["tool_calls"] == 2


def test_incomplete_lists_collected_evidence(make_agent):
    llm = ScriptedLLM([[("read_section", {"doc_id": "D01", "section_id": "s3", **R})],
                       [("search", {"query": "x", "top_k": 1, **R})]])
    res = make_agent(llm, max_llm_turns=2).run("q")
    assert res["status"] == "incomplete" and "D01#s3" in res["gaps"][0]


def test_repeated_gate_rejections_end_incomplete(make_agent):
    bad = _finish("answered", [{"doc_id": "D01", "section_id": "s3", "quote": "编造的内容"}])
    llm = ScriptedLLM([[bad], [bad], [bad]])
    res = make_agent(llm).run("q")
    assert res["status"] == "incomplete" and res["incomplete_reason"] == "gate_rejections_exhausted"


def test_ask_user_ends_with_need_clarification(make_agent):
    llm = ScriptedLLM([[("ask_user", {"question": "您的工龄是多少年？", **R})]])
    res = make_agent(llm).run("年假几天")
    assert res["status"] == "need_clarification" and res["clarifying_question"] == "您的工龄是多少年？"


def test_model_error(make_agent):
    res = make_agent(ScriptedLLM([LLMError("401 invalid key")])).run("q")
    assert res["status"] == "model_error" and "401" in res["gaps"][0]


def test_text_without_tool_is_not_accepted_as_answer(make_agent):
    llm = ScriptedLLM([make_response([], content="报销期限是 15 天"),
                       [("read_section", {"doc_id": "D05", "section_id": "s2", **R})],
                       [_finish("answered", CITE_D05)]])
    res = make_agent(llm).run("q")
    assert res["trace"][0]["action"] == "(text_without_tool)" and res["status"] == "answered"


def test_duplicate_call_is_flagged(make_agent):
    same = ("search", {"query": "报销", "top_k": 3, **R})
    llm = ScriptedLLM([[same], [same], [("ask_user", {"question": "?", **R})]])
    res = make_agent(llm).run("q")
    assert "参数完全相同" in res["trace"][1]["observation"]


def test_parallel_calls_and_invalid_json(make_agent):
    from src.llm.base import LLMResponse, ToolCall
    calls = [ToolCall("a", "outline", '{"doc_id": "D01", "reason": "x"}'), ToolCall("b", "outline", "{not json")]
    msg = {"role": "assistant", "content": "", "tool_calls": [
        {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in calls]}
    llm = ScriptedLLM([LLMResponse("", calls, msg), [("ask_user", {"question": "?", **R})]])
    res = make_agent(llm).run("q")
    assert res["trace"][0]["ok"] and not res["trace"][1]["ok"]
    assert {m.get("tool_call_id") for m in llm.contexts[1] if m["role"] == "tool"} == {"a", "b"}


def test_reasoning_content_is_echoed_back(make_agent):
    from src.llm.base import LLMResponse, ToolCall
    call = ToolCall("r1", "outline", '{"doc_id": "D01", "reason": "x"}')
    msg = {"role": "assistant", "content": "", "reasoning_content": "THINK",
           "tool_calls": [{"id": "r1", "type": "function", "function": {"name": "outline", "arguments": call.arguments}}]}
    llm = ScriptedLLM([LLMResponse("", [call], msg), [("ask_user", {"question": "?", **R})]])
    make_agent(llm).run("q")
    assert any(m.get("reasoning_content") == "THINK" for m in llm.contexts[1])


def test_history_is_included(make_agent):
    llm = ScriptedLLM([[("ask_user", {"question": "?", **R})]])
    make_agent(llm).run("那满 10 年呢？", history=[{"question": "我入职 3 年，年假几天？", "answer": "7 天",
                                                  "citations": [{"doc_id": "D07", "section_id": "s1"}]}])
    user = llm.contexts[0][1]["content"]
    assert "【对话历史】" in user and "D07#s1" in user and user.endswith("【当前问题】那满 10 年呢？")
