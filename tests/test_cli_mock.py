"""CLI + 离线 MockLLM 端到端（只验证流程，不代表真实模型效果）。"""
import json

import pytest

from src.main import main


def _run(capsys, *argv):
    code = main(["--quiet", "--mock", *argv])
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


@pytest.mark.parametrize("question,status", [
    ("每周可以远程办公几天？", "answered"),
    ("报销期限多久？", "conflict_needs_confirmation"),
    ("公司股票期权怎么行权？", "out_of_scope"),
])
def test_mock_statuses(capsys, question, status):
    code, res = _run(capsys, "--question", question)
    assert code == 0 and res["status"] == status and res["mode"] == "offline_mock"


def test_mock_kb_variant_changes_answer(capsys):
    _, res = _run(capsys, "--question", "报销期限多久？", "--kb", "no_conflict")
    assert res["status"] == "answered" and "30 天" in res["answer"] and res["kb"].endswith("no_conflict")


def test_mock_tool_failure(capsys):
    _, res = _run(capsys, "--question", "报销期限多久？", "--fail", "search:always")
    assert res["status"] == "tool_error" and res["fault_injection"] == "search:always"


def test_input_file_and_outputs(capsys, tmp_path):
    inp = tmp_path / "c.input.json"
    inp.write_text(json.dumps({"question": "报销期限多久？", "options": {"max_llm_turns": 1},
                               "expect": {"status_in": ["incomplete"]}}, ensure_ascii=False), encoding="utf-8")
    out, md = tmp_path / "o.json", tmp_path / "t.md"
    code, res = _run(capsys, "--input", str(inp), "--output", str(out), "--trace-md", str(md))
    assert code == 0 and res["status"] == "incomplete"
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "incomplete"
    assert "| # | 轮 | 动作 |" in md.read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", ['[]', '{"question": ""}', '{"question": "q", "history": "x"}'])
def test_invalid_input_exit_code(capsys, tmp_path, payload):
    inp = tmp_path / "bad.json"
    inp.write_text(payload, encoding="utf-8")
    assert main(["--quiet", "--mock", "--input", str(inp)]) == 2


def test_invalid_kb_exit_code(capsys, tmp_path):
    assert main(["--quiet", "--mock", "--question", "q", "--kb", str(tmp_path / "nope")]) == 2
