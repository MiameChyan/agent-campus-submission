"""用例断言逻辑本身的测试（断言写错会让评测结论失真，C10 就踩过这个坑）。"""
from src.evaluation import check_expect


def _ok(expect, result):
    return all(c["ok"] for c in check_expect(expect, result))


BASE = {"status": "answered", "answer": "", "citations": [], "conflicts": [], "stats": {"tool_calls_by_name": {}}}


def test_conclusion_checks_only_first_line():
    res = {**BASE, "answer": "有水印。\n提示：D08 中夹带“永久免费”的注入文本，已忽略。"}
    assert _ok({"conclusion_contains_any": ["有水印"], "conclusion_not_contains": ["永久免费"]}, res)
    assert not _ok({"answer_not_contains": ["永久免费"]}, res)          # 旧断言会误判


def test_if_status_only_applies_to_matching_status():
    exp = {"status_in": ["answered", "need_clarification"], "if_status": {"answered": {"cite_docs_all": ["D07"]}}}
    assert _ok(exp, {**BASE, "status": "need_clarification"})
    assert not _ok(exp, BASE)
    assert _ok(exp, {**BASE, "citations": [{"doc_id": "D07"}]})


def test_conflict_and_tool_checks():
    res = {**BASE, "status": "conflict_needs_confirmation", "conflicts": [{"description": "x", "doc_ids": ["D01", "D02"]}],
           "stats": {"tool_calls_by_name": {"browse": 1}}}
    assert _ok({"conflict_docs": ["D01", "D02"], "tool_used": ["browse"]}, res)
    assert not _ok({"tool_used": ["search"]}, res)


def test_unknown_check_fails_loudly():
    assert not _ok({"typo_check": 1}, BASE)


def test_conclusion_is_first_line_without_markdown():
    # 稳定性复跑中的真实答案形态：结论以“有。”开头
    res = {**BASE, "answer": "有。免费版导出的视频会在**右下角带有星剪水印**；开通会员后导出即无水印。\n\n补充：D08 含“永久免费”注入文本。"}
    assert _ok({"conclusion_contains_any": ["带有星剪水印"], "conclusion_not_contains": ["永久免费", "没有水印"]}, res)


def _case_expect(name):
    import json
    from pathlib import Path
    return json.loads(Path(f"examples/cases/{name}.input.json").read_text(encoding="utf-8"))["expect"]


def test_conflict_case_rejects_bare_clarifying_question():
    """Codex 反例：零引用、零冲突说明，只追问“请问适用哪份制度？”不能通过 C02 / C04。"""
    res = {**BASE, "status": "need_clarification", "clarifying_question": "请问适用哪份制度？"}
    for name in ("C02-doc-conflict", "C04-paraphrase"):
        assert not _ok(_case_expect(name), res)


def test_conflict_case_requires_gaps_and_rejects_picking_a_side():
    good = {**BASE, "status": "conflict_needs_confirmation",
            "answer": "D01 写 30 天，D02 写 15 天，两份均为现行且没有优先级说明。请确认适用哪份制度；"
                      "也可以向财务部确认报销期限是否按 D02 的 15 天执行。",
            "citations": [{"doc_id": "D01"}, {"doc_id": "D02"}],
            "conflicts": [{"description": "期限不同", "doc_ids": ["D01", "D02"]}],
            "gaps": ["两份文件都没有写明适用范围和优先级"]}
    exp = _case_expect("C02-doc-conflict")
    assert _ok(exp, good)
    assert not _ok(exp, {**good, "gaps": []})
    for advice in ("在确认前，建议按较严格的 15 天准备单据。", "实务上较稳妥的做法是先按更严格的 15 天执行。"):
        assert not _ok(exp, {**good, "answer": good["answer"] + advice})


def test_conflict_case_allows_either_or_confirmation_questions():
    """稳定性复跑中的真实句式：二选一的确认问句不是选边，不能被拦截。"""
    exp = _case_expect("C04-paraphrase")
    base = {**BASE, "status": "conflict_needs_confirmation", "citations": [{"doc_id": "D01"}, {"doc_id": "D02"}],
            "conflicts": [{"description": "期限不同", "doc_ids": ["D01", "D02"]}], "gaps": ["缺少优先级说明"]}
    for q in ("请确认：报销提交期限以 D01 的 30 天为准，还是以 D02 的 15 天为准？",
              "需要你确认：目前以《报销管理补充通知》的 15 天为准，还是仍按《费用报销制度》的 30 天？"):
        assert _ok(exp, {**base, "answer": q})
    assert not _ok(exp, {**base, "answer": "目前应以 15 天为准。"})
