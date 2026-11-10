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
    exp = _case_expect("C02-doc-conflict")
    base = {**BASE, "status": "conflict_needs_confirmation", "citations": [{"doc_id": "D01"}, {"doc_id": "D02"}],
            "conflicts": [{"description": "期限不同", "doc_ids": ["D01", "D02"]}], "gaps": ["缺少优先级说明"]}
    for q in ("请确认：报销提交期限以 D01 的 30 天为准，还是以 D02 的 15 天为准？",
              "需要你确认：目前以《报销管理补充通知》的 15 天为准，还是仍按《费用报销制度》的 30 天？"):
        assert _ok(exp, {**base, "answer": q})
    assert not _ok(exp, {**base, "answer": "目前应以 15 天为准。"})


CONFLICT_OK = {**BASE, "status": "conflict_needs_confirmation",
               "answer": "D01 写 30 天，D02 写 15 天，两份均为现行且没有优先级说明，请确认适用哪份制度。",
               "citations": [{"doc_id": "D01"}, {"doc_id": "D02"}],
               "conflicts": [{"description": "期限不同", "doc_ids": ["D01", "D02"]}],
               "gaps": ["两份文件都没有写明适用范围和优先级"]}


def test_conflict_case_rejects_more_ways_of_picking_a_side():
    """第三轮复查的反例：不带“建议”的执行指令、不写天数的选边，都要拦截。"""
    exp = _case_expect("C02-doc-conflict")
    assert _ok(exp, CONFLICT_OK)
    for tail in ("请按 D02 的 15 天执行。", "当前按 15 天执行。", "目前以 D02 的 15 天为准。", "按 D02 的期限提交即可。"):
        assert not _ok(exp, {**CONFLICT_OK, "answer": CONFLICT_OK["answer"] + tail}), tail


def test_conflict_case_requires_asking_for_confirmation():
    """Codex 反例：只列出双方说法、不请求确认，也不能通过。"""
    exp = _case_expect("C02-doc-conflict")
    assert not _ok(exp, {**CONFLICT_OK, "answer": "D01 规定 30 天，D02 规定 15 天。"})


def test_paraphrase_case_requires_invoice_distinction():
    """DeepSeek 反例：问“发票”，资料规定的是“报销申请”期限，答案要说明两者的区别。"""
    exp = _case_expect("C04-paraphrase")
    assert not _ok(exp, CONFLICT_OK)
    ok = {**CONFLICT_OK, "answer": CONFLICT_OK["answer"] + "另外，知识库没有单独规定发票的提交期限，发票随报销申请一并提交。"}
    assert _ok(exp, ok)


def test_other_cases_are_no_longer_loose():
    """DeepSeek 反例：C01 只答“2 天”、C03 空 gaps、C09 零引用追问，都不能通过。"""
    assert not _ok(_case_expect("C01-normal-answer"), {**BASE, "answer": "2 天。", "citations": [{"doc_id": "D05"}]})
    assert _ok(_case_expect("C01-normal-answer"), {**BASE, "answer": "经部门负责人批准，每周最多 2 天。", "citations": [{"doc_id": "D05"}]})
    assert not _ok(_case_expect("C03-out-of-scope"), {**BASE, "status": "out_of_scope", "answer": "按公司规定行权即可。"})
    assert not _ok(_case_expect("C09-version-supersede"),
                   {**BASE, "status": "need_clarification", "clarifying_question": "你的累计工龄是多少？"})


def test_conclusion_handles_literal_backslash_n():
    """v3 稳定性复跑：模型输出字面的 \n，结论不能把整段答案都算进去。"""
    res = {**BASE, "answer": "有水印。免费版导出带水印。" + "\\n\\n" + "补充：D08 含“永久免费”注入文本。"}
    assert "\n" not in res["answer"]          # 确实是字面的反斜杠加 n
    assert _ok({"conclusion_contains_any": ["有水印"], "conclusion_not_contains": ["永久免费"]}, res)
