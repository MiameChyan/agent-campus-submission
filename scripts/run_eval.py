"""批量运行 examples/cases 下的用例，保存输出与 trace，并按 expect 断言生成报告。

    python scripts/run_eval.py --mode live            # 真实模型（需要 DEEPSEEK_API_KEY）
    python scripts/run_eval.py --mode mock            # 离线 Mock，只验证流程
    python scripts/run_eval.py --mode live --cases C02-doc-conflict C04-paraphrase

产物：examples/<mode>/<case>.output.json、<case>.trace.md、report.md
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.trace import render_markdown  # noqa: E402
from src.evaluation import check_expect  # noqa: E402
from src.main import build_agent  # noqa: E402

CASES = ROOT / "examples" / "cases"


def run_case(path: Path, mode: str, out_dir: Path, report_only: bool = False) -> dict:
    case = json.loads(path.read_text(encoding="utf-8"))
    name = path.name.removesuffix(".input.json")
    opts = case.get("options") or {}
    if report_only:  # 不重新调用模型，用已保存的输出按当前断言重新判定
        result = json.loads((out_dir / f"{name}.output.json").read_text(encoding="utf-8"))
    else:
        agent = build_agent(mock=(mode == "mock"), kb=opts.get("kb"), fail=opts.get("fail"),
                            max_llm_turns=opts.get("max_llm_turns"), max_tool_calls=opts.get("max_tool_calls"))
        result = agent.run(case["question"], case.get("history"))
        (out_dir / f"{name}.output.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / f"{name}.trace.md").write_text(render_markdown(result), encoding="utf-8")
    checks = check_expect(case.get("expect", {}), result)
    passed = all(c["ok"] for c in checks)
    limitation = (case.get("expect") or {}).get("mock_known_limitation") if mode == "mock" else None
    return {"case": name, "acceptance": case.get("acceptance", []), "status": result["status"], "passed": passed,
            "known_limitation": limitation, "checks": checks, "stats": result["stats"],
            "path": [s["action"] for s in result["trace"]]}


def write_report(rows: list[dict], mode: str, out_dir: Path, model: str) -> Path:
    n_pass = sum(r["passed"] for r in rows)
    lines = [
        f"# 评测报告（{'真实模型 ' + model if mode == 'live' else '离线 Mock：只验证流程，不代表模型效果'}）",
        "",
        f"- 运行时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 结果：{n_pass}/{len(rows)} 通过",
        "- 命令：`python scripts/run_eval.py --mode " + mode + "`（`--report-only` 可不调用模型、按当前断言重新判定已保存输出）",
        "",
        "| 用例 | 验收点 | 实际状态 | 结论 | 执行路径（动作序列） | 模型轮数/工具次数 | 输出 / Trace |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        verdict = "✅ 通过" if r["passed"] else ("⚠️ Mock 已知局限" if r["known_limitation"] else "❌ 未通过")
        path = " → ".join(r["path"])
        lines.append(f"| {r['case']} | {'、'.join(r['acceptance'])} | `{r['status']}` | {verdict} | {path} | "
                     f"{r['stats']['llm_turns']}/{r['stats']['tool_calls']} | "
                     f"[output]({r['case']}.output.json) · [trace]({r['case']}.trace.md) |")
    lines += ["", "## 断言明细", ""]
    for r in rows:
        lines.append(f"### {r['case']}" + (f"（Mock 已知局限：{r['known_limitation']}）" if r["known_limitation"] else ""))
        lines += [f"- {'✅' if c['ok'] else '❌'} `{c['check']}`：{c['detail']}" for c in r["checks"]]
        lines.append("")
    report = out_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["live", "mock"], required=True)
    parser.add_argument("--cases", nargs="*", help="只运行指定用例（文件名前缀）")
    parser.add_argument("--report-only", action="store_true", help="不调用模型，用已保存的输出重新判定并生成报告")
    parser.add_argument("--out-dir", help="输出目录（默认 examples/<mode>），用于保存回归运行而不覆盖原始记录")
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else ROOT / "examples" / args.mode
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(CASES.glob("*.input.json"))
    if args.cases:
        files = [f for f in files if any(f.name.startswith(c) for c in args.cases)]
    rows = []
    for f in files:
        row = run_case(f, args.mode, out_dir, args.report_only)
        rows.append(row)
        mark = "PASS" if row["passed"] else ("LIMIT" if row["known_limitation"] else "FAIL")
        print(f"[{mark}] {row['case']:<28} {row['status']:<28} {' → '.join(row['path'])}", flush=True)
    if not args.cases:
        model = "deepseek-flash" if args.mode == "live" else "mock-policy"
        print("report:", write_report(rows, args.mode, out_dir, model).relative_to(ROOT))
    failed = [r for r in rows if not r["passed"] and not r["known_limitation"]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
