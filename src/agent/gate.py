"""提交闸门：finish 时校验引用是否真实、是否支撑结论。全部是确定性检查。

1. 引用真实：引用的小节必须在本次运行中用 read_section 读过；quote 必须逐字出现在原文中
   （只容忍首尾空白和连续空白的差别，删掉或增加空格、改写、拼接都会被拒）。
2. 依据有效：answered 不能只依据已废止文档；conflict_needs_confirmation 需要至少两份文档的引用和冲突描述。
3. 数值有据：答案中出现的业务数值（如“30 天”“5000 元”“1 个工作日”）必须出现在所引用小节的原文中，
   或出现在用户的问题 / 对话历史里。这能拦住“引文是真的，但结论与引文不符”的情况（如引用 30 天却回答 60 天）。
   日期、文档编号、条款序号不在核对范围内。数值以外的语义支撑无法机械判断，留给后续的异源模型评审。

闸门不替模型做业务决策：答案选哪个、是否判为冲突、是否追问，都由模型决定。
不通过时把具体原因作为观察退回给模型修正。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .state import RunState

_WS = re.compile(r"\s+")
MIN_QUOTE_CHARS = 4

# 业务数值：数字 + 单位
_UNITS = r"(个工作日|工作日|个月|天|日|年|周|小时|分钟|元|万元|%|％|次|人|倍|P)"
_FACT = re.compile(r"(\d+(?:\.\d+)?)\s*" + _UNITS)
# 日期类表达先剔除，避免把“2025 年 1 月 1 日”当成业务数值
_DATES = [
    re.compile(r"\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}"),
    re.compile(r"\d{4}\s*年(\s*\d{1,2}\s*月(\s*\d{1,2}\s*日)?)?"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日"),
]


def _ws(s: str) -> str:
    """只规范化空白：首尾去掉、连续空白合并为一个空格（不删除空格）。"""
    return _WS.sub(" ", s or "").strip()


def _numeric_facts(text: str) -> set[tuple[str, str]]:
    for pat in _DATES:
        text = pat.sub(" ", text)
    out = set()
    for num, unit in _FACT.findall(text):
        unit = {"％": "%", "工作日": "个工作日"}.get(unit, unit)
        out.add((num, unit))
    return out


@dataclass
class GateResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)   # 校验通过并补全元数据的引用


def check_finish(args: dict, state: RunState) -> GateResult:
    status = args.get("status")
    answer = args.get("answer") or ""
    citations = args.get("citations") or []
    conflicts = args.get("conflicts") or []
    problems: list[str] = []
    valid: list[dict] = []

    if not answer.strip():
        problems.append("answer 为空：请给出回答或说明无法回答的原因。")

    # ---- 1. 引用真实 ----
    for i, c in enumerate(citations, 1):
        doc_id = str(c.get("doc_id", "")).strip().upper()
        sec_id = str(c.get("section_id", "")).strip()
        ref = f"{doc_id}#{sec_id}"
        quote = _ws(c.get("quote", ""))
        ev = state.evidence.get(ref)
        if ev is None:
            problems.append(f"引用{i} {ref}：本次运行没有用 read_section 读取过该小节原文，不能引用。")
            continue
        if len(quote.replace(" ", "")) < MIN_QUOTE_CHARS:
            problems.append(f"引用{i} {ref}：quote 过短，请逐字复制能支持结论的原文片段。")
            continue
        if quote not in _ws(ev.text):
            problems.append(f"引用{i} {ref}：quote 与原文不一致，必须逐字复制原文中的连续片段"
                            "（包括原文中的空格和标点，不能改写、删减或拼接）。")
            continue
        valid.append({
            "doc_id": ev.doc_id, "section_id": ev.section_id, "title": ev.title,
            "section_title": ev.section_title, "version_date": ev.version_date,
            "doc_status": ev.status, "quote": quote,
        })

    # ---- 2. 依据有效 ----
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

    # ---- 3. 数值有据：答案中的业务数值必须能在所引用的原文（或用户输入）中找到 ----
    if status in ("answered", "conflict_needs_confirmation") and valid:
        cited_refs = {f"{v['doc_id']}#{v['section_id']}" for v in valid}
        supported = set()
        for ref in cited_refs:
            supported |= _numeric_facts(state.evidence[ref].text)
        supported |= _numeric_facts(state.context_text)
        missing = sorted(_numeric_facts(answer) - supported)
        if missing:
            shown = "、".join(f"“{n} {u}”" for n, u in missing[:5])
            problems.append(f"答案中的数值 {shown} 在所引用的原文中找不到"
                            f"（已引用：{'、'.join(sorted(cited_refs))}）。请核对结论是否与原文一致，"
                            "或补充引用能支持该数值的原文。")

    return GateResult(ok=not problems, problems=problems, citations=valid)
