"""工具执行、故障注入与提交闸门。"""
import pytest

from src.agent.gate import check_finish
from src.agent.state import EvidenceItem, RunState
from src.tools.base import ToolExecutionError
from src.tools.faults import FaultInjector
from src.tools.registry import build_tools, execute_business_tool


def test_all_schemas_are_strict(kb):
    for tool in build_tools(kb).values():
        params = tool.schema()["function"]["parameters"]
        assert params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"]) and "reason" in params["properties"]


def test_fault_injection_once_then_recover(kb):
    tools, faults = build_tools(kb), FaultInjector("search:1")
    with pytest.raises(ToolExecutionError) as exc:
        execute_business_tool(tools["search"], {"query": "报销", "top_k": 3}, faults)
    assert exc.value.retryable
    assert execute_business_tool(tools["search"], {"query": "报销", "top_k": 3}, faults)["hits"]


def test_fault_injection_always(kb):
    tools, faults = build_tools(kb), FaultInjector("search:always,browse:always")
    for _ in range(3):
        with pytest.raises(ToolExecutionError):
            execute_business_tool(tools["search"], {"query": "报销", "top_k": 3}, faults)
    with pytest.raises(ToolExecutionError):
        execute_business_tool(tools["browse"], {"path": ""}, faults)
    assert execute_business_tool(tools["outline"], {"doc_id": "D01"}, faults)["doc_id"] == "D01"


def test_invalid_fault_spec():
    with pytest.raises(ValueError):
        FaultInjector("search:sometimes")


def test_not_found_is_non_retryable(kb):
    with pytest.raises(ToolExecutionError) as exc:
        execute_business_tool(build_tools(kb)["read_section"], {"doc_id": "D01", "section_id": "s9"}, None)
    assert exc.value.error_type == "NotFound" and not exc.value.retryable


# ---------------- 提交闸门 ----------------
def _state_with(kb, *refs) -> RunState:
    st = RunState(8, 12)
    for ref in refs:
        doc_id, sec = ref.split("#")
        d = kb.read_section(doc_id, sec)
        st.evidence[ref] = EvidenceItem(ref, d["doc_id"], d["section_id"], d["title"], d["section_title"], d["version_date"],
                                        d["status"], d["scope"], d["supersedes"], d["superseded_by"], d["text"])
    return st


def _finish(status, citations, conflicts=None, answer="回答"):
    return {"status": status, "answer": answer, "citations": citations, "conflicts": conflicts or [], "gaps": []}


def test_gate_accepts_verbatim_quote(kb):
    st = _state_with(kb, "D01#s3")
    r = check_finish(_finish("answered", [{"doc_id": "D01", "section_id": "s3", "quote": "30 天内提交报销申请"}]), st)
    assert r.ok and r.citations[0]["version_date"] == "2024-03-01"


def test_gate_rejects_unread_section(kb):
    st = _state_with(kb, "D01#s3")
    r = check_finish(_finish("answered", [{"doc_id": "D02", "section_id": "s1", "quote": "15 天内提交"}]), st)
    assert not r.ok and "没有用 read_section 读取过" in r.problems[0]


def test_gate_rejects_paraphrased_quote(kb):
    st = _state_with(kb, "D01#s3")
    r = check_finish(_finish("answered", [{"doc_id": "D01", "section_id": "s3", "quote": "报销须在一个月内提交"}]), st)
    assert not r.ok and "连续片段" in r.problems[0]


def test_gate_rejects_answer_based_only_on_superseded_doc(kb):
    st = _state_with(kb, "D03#s1")
    r = check_finish(_finish("answered", [{"doc_id": "D03", "section_id": "s1", "quote": "年假 5 天"}]), st)
    assert not r.ok and "已废止" in r.problems[0]


def test_gate_conflict_needs_two_docs_and_description(kb):
    st = _state_with(kb, "D01#s3", "D02#s1")
    one = check_finish(_finish("conflict_needs_confirmation", [{"doc_id": "D01", "section_id": "s3", "quote": "30 天内提交报销申请"}]), st)
    assert not one.ok
    two = check_finish(_finish("conflict_needs_confirmation", [
        {"doc_id": "D01", "section_id": "s3", "quote": "30 天内提交报销申请"},
        {"doc_id": "D02", "section_id": "s1", "quote": "15 天内提交"},
    ], conflicts=[{"description": "期限不同", "doc_ids": ["D01", "D02"]}]), st)
    assert two.ok


def test_gate_allows_out_of_scope_without_citations(kb):
    assert check_finish(_finish("out_of_scope", [], answer="资料外"), RunState(8, 12)).ok
