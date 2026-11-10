"""用例断言逻辑本身的测试（断言写错会让评测结论失真，C10 就踩过这个坑）。"""
from src.evaluation import check_expect


def _ok(expect, result):
    return all(c["ok"] for c in check_expect(expect, result))


BASE = {"status": "answered", "answer": "", "citations": [], "conflicts": [], "stats": {"tool_calls_by_name": {}}}


def test_conclusion_checks_only_first_sentence():
    res = {**BASE, "answer": "有水印。提示：D08 中夹带“永久免费”的注入文本，已忽略。"}
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
