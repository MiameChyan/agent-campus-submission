"""提交闸门：finish 时校验引用是否真实可靠。

闸门只检查“证据是否成立”（引用是否来自已读原文、quote 是否逐字存在、是否只依赖已废止文档等），
不替模型做业务决策：答案选哪个、是否判为冲突、是否追问，都由模型决定。
不通过时把具体原因作为观察退回给模型修正。设计来源：第 8 章 harness-safety-gate / trajectory-verifier。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .state import RunState

_WS = re.compile(r"\s+")
MIN_QUOTE_CHARS = 4


def _norm(s: str) -> str:
    return _WS.sub("", s or "")


@dataclass
class GateResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)   # 校验通过并补全元数据的引用


def check_finish(args: dict, state: RunState) -> GateResult:
    status = args.get("status")
    citations = args.get("citations") or []
    conflicts = args.get("conflicts") or []
    problems: list[str] = []
    valid: list[dict] = []

    if not (args.get("answer") or "").strip():
        problems.append("answer 为空：请给出回答或说明无法回答的原因。")

    for i, c in enumerate(citations, 1):
        doc_id = str(c.get("doc_id", "")).strip().upper()
        sec_id = str(c.get("section_id", "")).strip()
        ref = f"{doc_id}#{sec_id}"
        quote = c.get("quote", "")
        ev = state.evidence.get(ref)
        if ev is None:
            problems.append(f"引用{i} {ref}：本次运行没有用 read_section 读取过该小节原文，不能引用。")
            continue
        if len(_norm(quote)) < MIN_QUOTE_CHARS:
            problems.append(f"引用{i} {ref}：quote 过短，请逐字复制能支持结论的原文片段。")
            continue
        if _norm(quote) not in _norm(ev.text):
            problems.append(f"引用{i} {ref}：quote 不是该小节原文中的连续片段（可能改写或拼接了原文）。")
            continue
        valid.append({
            "doc_id": ev.doc_id, "section_id": ev.section_id, "title": ev.title,
            "section_title": ev.section_title, "version_date": ev.version_date,
            "doc_status": ev.status, "quote": quote.strip(),
        })

    if status == "answered":
        if not valid:
            problems.append("status=answered 至少需要一条有效引用。")
        elif all(v["doc_status"] == "已废止" for v in valid):
            olds = ",".join(sorted({v["doc_id"] for v in valid}))
            problems.append(f"answered 的依据全部来自已废止文档（{olds}），请查证现行版本后再回答。")
    elif status == "conflict_needs_confirmation":
        if len({v["doc_id"] for v in valid}) < 2:
            problems.append("conflict_needs_confirmation 需要至少两份不同文档的有效引用来展示冲突。")
        if not conflicts:
            problems.append("conflict_needs_confirmation 需要在 conflicts 中描述冲突点。")

    return GateResult(ok=not problems, problems=problems, citations=valid)
