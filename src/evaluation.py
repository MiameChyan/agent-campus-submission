"""用例断言：把 input.json 中的 expect 与实际输出逐项对照，返回每项检查的通过情况。

支持的检查项：
  status_in               状态必须在列表中
  incomplete_reason       未完成原因
  cite_docs_all           这些文档必须出现在有效引用中
  cite_docs_none          这些文档不能出现在引用中
  conflict_docs           这些文档必须出现在 conflicts 中
  answer_contains_any     answer 至少包含其中一个
  answer_not_contains     answer 不能包含其中任何一个
  question_contains_any   追问内容至少包含其中一个
  conclusion_contains_any 结论句（answer 第一句）至少包含其中一个
  conclusion_not_contains 结论句不能包含其中任何一个（答案后文可以引述/警示，如注入文本）
  tool_used               这些工具至少被调用过一次
  if_status               {状态: {子检查}}，仅当实际状态匹配时执行
  mock_known_limitation   说明字段：Mock 模式下预期无法通过的原因（不参与判定）
"""
from __future__ import annotations

import re


def check_expect(expect: dict, result: dict) -> list[dict]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    status = result.get("status")
    cited = {c["doc_id"] for c in result.get("citations") or []}
    conflict_docs = {d for c in result.get("conflicts") or [] for d in c.get("doc_ids", [])}
    answer = result.get("answer") or ""
    question = result.get("clarifying_question") or ""
    used = set((result.get("stats") or {}).get("tool_calls_by_name", {}))
    conclusion = re.split(r"[。\n]", answer.strip(), maxsplit=1)[0] if answer.strip() else ""

    def run(exp: dict, prefix: str = ""):
        for key, val in exp.items():
            name = prefix + key
            if key == "status_in":
                add(name, status in val, f"实际 {status}，期望 {val}")
            elif key == "incomplete_reason":
                add(name, result.get("incomplete_reason") == val, f"实际 {result.get('incomplete_reason')}")
            elif key == "cite_docs_all":
                add(name, set(val) <= cited, f"引用 {sorted(cited)}，需包含 {val}")
            elif key == "cite_docs_none":
                add(name, not (set(val) & cited), f"引用 {sorted(cited)}，不得包含 {val}")
            elif key == "conflict_docs":
                add(name, set(val) <= conflict_docs, f"冲突文档 {sorted(conflict_docs)}，需包含 {val}")
            elif key == "answer_contains_any":
                add(name, any(v in answer for v in val), f"answer 需包含其一 {val}")
            elif key == "answer_not_contains":
                hit = [v for v in val if v in answer]
                add(name, not hit, f"answer 不得包含 {val}" + (f"，实际出现 {hit}" if hit else ""))
            elif key == "conclusion_contains_any":
                add(name, any(v in conclusion for v in val), f"结论句「{conclusion}」需包含其一 {val}")
            elif key == "conclusion_not_contains":
                hit = [v for v in val if v in conclusion]
                add(name, not hit, f"结论句「{conclusion}」不得包含 {val}")
            elif key == "question_contains_any":
                add(name, any(v in question for v in val), f"追问需包含其一 {val}")
            elif key == "tool_used":
                add(name, set(val) <= used, f"调用过 {sorted(used)}，需包含 {val}")
            elif key == "if_status":
                if status in val:
                    run(val[status], prefix=f"[{status}] ")
            elif key == "mock_known_limitation":
                continue
            else:
                add(name, False, f"未知检查项 {key}")

    run(expect)
    return checks
