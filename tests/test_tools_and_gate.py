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


def _finish(status, citations, conflicts=None, answer="回答", gaps=None):
    if gaps is None:   # 冲突状态默认带上资料缺口，其他状态默认为空
        gaps = ["两份文件都没有写明适用范围和优先级"] if status == "conflict_needs_confirmation" else []
    return {"status": status, "answer": answer, "citations": citations, "conflicts": conflicts or [], "gaps": gaps}


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


# ---------- 外部评审（Codex）指出的问题：引文真实 ≠ 支撑结论；逐字匹配不能忽略空格 ----------
CITE_30 = [{"doc_id": "D01", "section_id": "s3", "quote": "员工应在费用发生之日起 30 天内提交报销申请"}]


def test_gate_rejects_conclusion_not_supported_by_quote(kb):
    r = check_finish(_finish("answered", CITE_30, answer="报销期限是 60 天。"), _state_with(kb, "D01#s3"))
    assert not r.ok and "60 天" in r.problems[0]


def test_gate_accepts_number_present_in_cited_section(kb):
    # 引文只截了一部分，但数值出现在所引用小节的原文里，也算有据
    cite = [{"doc_id": "D07", "section_id": "s1", "quote": "满 10 年不满 20 年的，年假 12 天"}]
    r = check_finish(_finish("answered", cite, answer="满 10 年不满 20 年 12 天；满 20 年 15 天。"), _state_with(kb, "D07#s1"))
    assert r.ok, r.problems


def test_gate_rejects_number_only_in_uncited_section(kb):
    # 读过 D03（5 天）但没有引用它，答案里的 5 天不能算有据
    st = _state_with(kb, "D07#s1", "D03#s1")
    cite = [{"doc_id": "D07", "section_id": "s1", "quote": "满 1 年不满 10 年的，年假 7 天"}]
    r = check_finish(_finish("answered", cite, answer="现行 7 天，旧版曾是 5 天。"), st)
    assert not r.ok and "5 天" in r.problems[0]


def test_gate_ignores_dates(kb):
    r = check_finish(_finish("answered", CITE_30, answer="依据 2024-03-01 版（2024 年 3 月 1 日施行）：30 天。"), _state_with(kb, "D01#s3"))
    assert r.ok, r.problems


def test_gate_numbers_in_question_are_not_evidence(kb):
    """Codex 反例：问“报销期限是 60 天吗？”，答“是，60 天”并引用写着 30 天的原文，不能通过。"""
    r = check_finish(_finish("answered", CITE_30, answer="是的，报销期限是 60 天。"), _state_with(kb, "D01#s3"))
    assert not r.ok and "60 天" in r.problems[0]


def test_gate_rejects_quote_with_spaces_removed(kb):
    cite = [{"doc_id": "D01", "section_id": "s3", "quote": "员工应在费用发生之日起30天内提交报销申请"}]
    r = check_finish(_finish("answered", cite, answer="30 天。"), _state_with(kb, "D01#s3"))
    assert not r.ok and "逐字" in r.problems[0]


def test_gate_tolerates_only_outer_and_repeated_whitespace(kb):
    cite = [{"doc_id": "D01", "section_id": "s3", "quote": "  员工应在费用发生之日起  30 天内提交报销申请 "}]
    assert check_finish(_finish("answered", cite, answer="30 天。"), _state_with(kb, "D01#s3")).ok


def test_gate_checks_numbers_in_conflict_answer(kb):
    st = _state_with(kb, "D01#s3", "D02#s1")
    cites = CITE_30 + [{"doc_id": "D02", "section_id": "s1", "quote": "员工报销申请应在费用发生后 15 天内提交"}]
    conflicts = [{"description": "期限不同", "doc_ids": ["D01", "D02"]}]
    assert check_finish(_finish("conflict_needs_confirmation", cites, conflicts, answer="D01 为 30 天，D02 为 15 天。"), st).ok
    bad = check_finish(_finish("conflict_needs_confirmation", cites, conflicts, answer="D01 为 30 天，D02 为 10 天。"), st)
    assert not bad.ok and "10 天" in bad.problems[0]


# ---------- 第三轮外部复查（Codex + DeepSeek）的反例 ----------
CITE_D07 = [{"doc_id": "D07", "section_id": "s1", "quote": "员工累计工作满 1 年不满 10 年的，年假 7 天"}]


def test_gate_rejects_condition_value_mismatch(kb):
    """Codex 反例：“满 10 年”和“7 天”都出现在 D07 同一小节，但不在同一个分句里。"""
    r = check_finish(_finish("answered", CITE_D07, answer="满 10 年有 7 天。"), _state_with(kb, "D07#s1"))
    assert not r.ok and "条件" in r.problems[0]


def test_gate_accepts_correct_condition_value_pairs(kb):
    ans = "- 满 1 年不满 10 年：年假 7 天\n- 满 10 年不满 20 年：年假 **12 天**\n- 满 20 年：年假 15 天"
    assert check_finish(_finish("answered", CITE_D07, answer=ans), _state_with(kb, "D07#s1")).ok
    assert check_finish(_finish("answered", CITE_D07, answer="满 10 年的员工年假 12 天。"), _state_with(kb, "D07#s1")).ok


def test_gate_converts_chinese_numerals(kb):
    """DeepSeek 反例：“六十天”配 30 天的原文。"""
    bad = check_finish(_finish("answered", CITE_30, answer="报销期限是六十天。"), _state_with(kb, "D01#s3"))
    assert not bad.ok and "60 天" in bad.problems[0]
    assert check_finish(_finish("answered", CITE_30, answer="报销期限是三十天。"), _state_with(kb, "D01#s3")).ok


def test_gate_conflict_requires_gaps(kb):
    st = _state_with(kb, "D01#s3", "D02#s1")
    cites = CITE_30 + [{"doc_id": "D02", "section_id": "s1", "quote": "员工报销申请应在费用发生后 15 天内提交"}]
    r = check_finish(_finish("conflict_needs_confirmation", cites, [{"description": "期限不同", "doc_ids": ["D01", "D02"]}],
                             answer="D01 为 30 天，D02 为 15 天，请确认适用哪份制度。", gaps=[]), st)
    assert not r.ok and "gaps" in r.problems[0]


def test_gate_conflict_doc_ids_must_be_cited(kb):
    st = _state_with(kb, "D01#s3", "D02#s1")
    cites = CITE_30 + [{"doc_id": "D02", "section_id": "s1", "quote": "员工报销申请应在费用发生后 15 天内提交"}]
    r = check_finish(_finish("conflict_needs_confirmation", cites, [{"description": "期限不同", "doc_ids": ["D05", "D06"]}],
                             answer="D01 为 30 天，D02 为 15 天。"), st)
    assert not r.ok and "D05" in r.problems[0]


def test_gate_out_of_scope_and_tool_error_cannot_cite(kb):
    """Codex 复跑中出现过：问股票期权返回 out_of_scope，却附上了无关的 D01 引文。"""
    for status in ("out_of_scope", "tool_error"):
        r = check_finish(_finish(status, CITE_30, answer="资料外"), _state_with(kb, "D01#s3"))
        assert not r.ok and "不应携带引用" in r.problems[0]


def test_gate_pairs_conditions_with_the_nearest_value(kb):
    """回放 v2 的 C05 时发现的误伤：一句话列出三档，应逐对核对，而不是把整句当成一组。"""
    ans = "依据 D07 第一条：满 1 年不满 10 年 7 天，满 10 年不满 20 年 12 天，满 20 年 15 天。"
    assert check_finish(_finish("answered", CITE_D07, answer=ans), _state_with(kb, "D07#s1")).ok
    swapped = "依据 D07 第一条：满 1 年不满 10 年 12 天，满 10 年不满 20 年 7 天。"
    assert not check_finish(_finish("answered", CITE_D07, answer=swapped), _state_with(kb, "D07#s1")).ok


def test_gate_does_not_treat_idioms_as_numbers(kb):
    """v3 稳定性复跑中的误伤：“同一天”“哪一天”被换算成“1 天”，模型无法定位，连续退回 3 次。"""
    ans = "D01 为 30 天，D02 为 15 天，两份文件不是同一天发布的；请确认适用哪份制度，以及从哪一天起算。"
    st = _state_with(kb, "D01#s3", "D02#s1")
    cites = CITE_30 + [{"doc_id": "D02", "section_id": "s1", "quote": "员工报销申请应在费用发生后 15 天内提交"}]
    assert check_finish(_finish("conflict_needs_confirmation", cites, [{"description": "期限不同", "doc_ids": ["D01", "D02"]}], answer=ans), st).ok


def test_gate_message_shows_original_wording(kb):
    r = check_finish(_finish("answered", CITE_30, answer="报销期限是六十天。"), _state_with(kb, "D01#s3"))
    assert "答案中写作“六十天”" in r.problems[0]


def test_gate_does_not_read_wei_yi_nian_as_one_year(kb):
    """离线回放 v1 时发现的误伤：“唯一年限”被读成“1 年”。"""
    st = _state_with(kb, "D01#s3", "D02#s1")
    cites = CITE_30 + [{"doc_id": "D02", "section_id": "s1", "quote": "员工报销申请应在费用发生后 15 天内提交"}]
    ans = "两份文件说法不一致，无法给出唯一年限或天数：D01 为 30 天，D02 为 15 天，请确认适用哪份制度。"
    assert check_finish(_finish("conflict_needs_confirmation", cites, [{"description": "期限不同", "doc_ids": ["D01", "D02"]}], answer=ans), st).ok
