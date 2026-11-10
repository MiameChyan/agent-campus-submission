"""离线回放提交闸门：用当前闸门重新校验已保存的真实模型输出（不调用模型）。

用于修改闸门后检查两件事：新规则会不会误伤以前正确的答案；以前放过的答案里有没有新规则能发现的问题。

    python scripts/replay_gate.py                       # 回放 examples/live 下的全部输出
    python scripts/replay_gate.py examples/live/v1-initial
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.gate import check_finish  # noqa: E402
from src.agent.state import EvidenceItem, RunState  # noqa: E402
from src.config import resolve_kb  # noqa: E402
from src.kb.retrievers import BM25Retriever  # noqa: E402
from src.kb.store import KnowledgeBase  # noqa: E402

_KB_CACHE: dict[str, KnowledgeBase] = {}


def _kb(label: str) -> KnowledgeBase:
    if label not in _KB_CACHE:
        _KB_CACHE[label] = KnowledgeBase.load(resolve_kb(label), retriever=BM25Retriever())
    return _KB_CACHE[label]


def replay(path: Path) -> tuple[bool, list[str]]:
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("status") not in ("answered", "conflict_needs_confirmation", "out_of_scope", "tool_error"):
        return True, []
    kb = _kb(r.get("kb") or "data/kb")
    state = RunState(8, 12)
    for c in r.get("citations") or []:        # 已保存的引用都来自当次读过的原文
        d = kb.read_section(c["doc_id"], c["section_id"])
        ref = f"{d['doc_id']}#{d['section_id']}"
        state.evidence[ref] = EvidenceItem(ref, d["doc_id"], d["section_id"], d["title"], d["section_title"],
                                           d["version_date"], d["status"], d["scope"], d["supersedes"],
                                           d["superseded_by"], d["text"])
    args = {"status": r["status"], "answer": r.get("answer", ""), "conflicts": r.get("conflicts") or [],
            "gaps": r.get("gaps") or [],
            "citations": [{"doc_id": c["doc_id"], "section_id": c["section_id"], "quote": c["quote"]}
                          for c in r.get("citations") or []]}
    g = check_finish(args, state)
    return g.ok, g.problems


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    roots = [Path(a).resolve() for a in (argv or sys.argv[1:])] or [ROOT / "examples" / "live"]
    files = sorted(f for r in roots for f in r.rglob("*.output.json"))
    bad = 0
    for f in files:
        ok, problems = replay(f)
        if not ok:
            bad += 1
            print(f"[REJECT] {f.relative_to(ROOT).as_posix()}")
            for p in problems:
                print(f"         - {p}")
    print(f"回放 {len(files)} 份输出：{len(files) - bad} 份通过当前闸门，{bad} 份会被退回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
