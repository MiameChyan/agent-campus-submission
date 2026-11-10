"""CLI 评审入口。

    python -m src.main --input examples/cases/C01-normal-answer.input.json
    python -m src.main --question "报销期限多久？" [--mock] [--kb no_conflict] [--fail search:always]

输入 JSON：{"question": str, "history": [{"question","answer","citations"}]?, "options": {...}?, "expect": {...}?}
options 可含 kb / fail / max_llm_turns / max_tool_calls，命令行参数优先。expect 只供评测脚本使用，Agent 忽略。
标准输出为结果 JSON；过程步骤打印到标准错误。业务状态（含失败/未完成）均以 JSON 返回、退出码 0；
输入或知识库非法时退出码 2。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent.harness import Agent
from .agent.trace import render_markdown
from .config import ROOT, RetrievalSettings, default_budget, resolve_kb
from .kb.retrievers import RETRIEVERS, RetrieverError, create_retriever
from .kb.store import KBValidationError, KnowledgeBase
from .llm.base import LLMError
from .llm.openai_compat import create_llm
from .llm.providers import PROVIDERS
from .tools.faults import FaultInjector


def build_agent(*, mock: bool, kb: str | None, fail: str | None, max_llm_turns: int | None,
                max_tool_calls: int | None, on_event=None, provider: str | None = None,
                model: str | None = None, retriever: str | None = None) -> Agent:
    """组装一次运行：知识库 + 检索器（可插拔）+ 模型（可切换提供方）+ 工具（插件热加载）。"""
    kb_path = resolve_kb(kb)
    try:
        knowledge = KnowledgeBase.load(kb_path, retriever=create_retriever(RetrievalSettings.from_env(retriever)))
    except RetrieverError as exc:
        raise ValueError(f"检索器初始化失败：{exc}") from exc
    turns, calls = default_budget()
    if mock:
        from .llm.mock import MockLLM
        llm = MockLLM()
    else:
        llm = create_llm(provider, model)
    try:
        kb_label = Path(kb_path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        kb_label = str(kb_path)
    return Agent(llm, knowledge, max_llm_turns=max_llm_turns or turns, max_tool_calls=max_tool_calls or calls,
                 faults=FaultInjector(fail), on_event=on_event, kb_label=kb_label)


def load_request(args) -> dict:
    if args.input:
        req = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        req = {"question": args.question}
    if not isinstance(req, dict):
        raise ValueError("输入必须是 JSON 对象")
    q = req.get("question")
    if not isinstance(q, str) or not q.strip():
        raise ValueError("question 必须是非空字符串")
    hist = req.get("history") or []
    if not isinstance(hist, list) or not all(isinstance(h, dict) and isinstance(h.get("question"), str) for h in hist):
        raise ValueError("history 必须是 [{question, answer, citations?}] 列表")
    opts = req.get("options") or {}
    if not isinstance(opts, dict):
        raise ValueError("options 必须是对象")
    return req


def _print_event(event: dict) -> None:
    if event["type"] != "step":
        return
    s = event["step"]
    mark = "✓" if s.get("ok") else "✗"
    args = json.dumps(s.get("args", {}), ensure_ascii=False)
    print(f"[{s['step']:>2}|轮{s['turn']}] {mark} {s['action']} {args}\n      → {s['observation']}"
          + (f"\n      依据：{s['reason']}" if s.get("reason") else ""), file=sys.stderr)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="企业知识问答 Agent（CLI）")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="输入 JSON 文件")
    src.add_argument("--question", help="直接提问")
    parser.add_argument("--mock", action="store_true", help="离线 Mock 模型（只验证流程，不代表真实模型效果）")
    parser.add_argument("--kb", help="知识库目录或变体名（如 no_conflict）")
    parser.add_argument("--fail", help="故障注入，如 search:1 / search:always,browse:always")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), help="模型提供方，默认取 LLM_PROVIDER（deepseek）")
    parser.add_argument("--model", help="模型名，默认取提供方配置")
    parser.add_argument("--retriever", choices=RETRIEVERS, help="检索方式，默认取 RETRIEVER（bm25）")
    parser.add_argument("--max-llm-turns", type=int)
    parser.add_argument("--max-tool-calls", type=int)
    parser.add_argument("--output", help="把结果 JSON 写入文件")
    parser.add_argument("--trace-md", help="把 Markdown 版 trace 写入文件")
    parser.add_argument("--quiet", action="store_true", help="不打印过程步骤")
    args = parser.parse_args(argv)

    try:
        req = load_request(args)
        opts = req.get("options") or {}
        agent = build_agent(
            mock=args.mock,
            kb=args.kb or opts.get("kb"),
            fail=args.fail or opts.get("fail"),
            max_llm_turns=args.max_llm_turns or opts.get("max_llm_turns"),
            max_tool_calls=args.max_tool_calls or opts.get("max_tool_calls"),
            on_event=None if args.quiet else _print_event,
            provider=args.provider or opts.get("provider"),
            model=args.model or opts.get("model"),
            retriever=args.retriever or opts.get("retriever"),
        )
    except (OSError, ValueError, KBValidationError, LLMError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    result = agent.run(req["question"], req.get("history"))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.trace_md:
        Path(args.trace_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.trace_md).write_text(render_markdown(result), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
