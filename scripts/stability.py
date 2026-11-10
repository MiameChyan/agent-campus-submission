"""稳定性复跑：同一用例用真实模型重复运行 N 次，统计状态与断言通过情况。

    python scripts/stability.py --cases C02-doc-conflict C04-paraphrase C10-prompt-injection --runs 3
    python scripts/stability.py --report-only      # 不调用模型，按当前断言重新判定已保存输出

产物：examples/live/stability/<case>.run<i>.output.json 与 report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation import check_expect  # noqa: E402
from src.main import build_agent  # noqa: E402

OUT = ROOT / "examples" / "live" / "stability"
CASES = ROOT / "examples" / "cases"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cases", nargs="*", default=["C02-doc-conflict", "C04-paraphrase", "C10-prompt-injection"])
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows, n_ok, n_all = [], 0, 0
    for name in args.cases:
        case = json.loads((CASES / f"{name}.input.json").read_text(encoding="utf-8"))
        opts = case.get("options") or {}
        for i in range(1, args.runs + 1):
            out = OUT / f"{name}.run{i}.output.json"
            if args.report_only:
                if not out.exists():
                    continue
                result = json.loads(out.read_text(encoding="utf-8"))
            else:
                agent = build_agent(mock=False, kb=opts.get("kb"), fail=opts.get("fail"),
                                    max_llm_turns=opts.get("max_llm_turns"), max_tool_calls=opts.get("max_tool_calls"))
                result = agent.run(case["question"], case.get("history"))
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ok = all(c["ok"] for c in check_expect(case.get("expect", {}), result))
            n_ok, n_all = n_ok + ok, n_all + 1
            s = result["stats"]
            rows.append(f"| {name} | {i} | `{result['status']}` | {'✅' if ok else '❌'} | {s['llm_turns']}/{s['tool_calls']} | "
                        f"{' → '.join(t['action'] for t in result['trace'])} | [output]({out.name}) |")
            print(rows[-1], flush=True)
    md = ["# 稳定性复跑（真实模型 deepseek-flash）", "",
          f"- 结果：{n_ok}/{n_all} 通过", "- 命令：`python scripts/stability.py`（`--report-only` 按当前断言重新判定已保存输出）", "",
          "| 用例 | 第几次 | 状态 | 断言 | 模型轮数/工具次数 | 执行路径 | 输出 |", "|---|---|---|---|---|---|---|", *rows, ""]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    return 0 if n_ok == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
