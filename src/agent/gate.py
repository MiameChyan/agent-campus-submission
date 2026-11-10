"""提交闸门：finish 时校验引用是否真实、是否支撑结论。全部是确定性检查。

1. 引用真实：引用的小节必须在本次运行中用 read_section 读过；quote 必须逐字出现在原文中
   （只容忍首尾空白和连续空白的差别，删掉或增加空格、改写、拼接都会被拒）。
2. 状态与引用相符：
   - answered：至少一条有效引用，且不能只依据已废止文档；
   - conflict_needs_confirmation：至少两份文档的引用、非空的冲突描述，冲突涉及的文档必须是已引用的文档，
     并且 gaps 不能为空（要说明查证后还缺什么信息）；
   - out_of_scope / tool_error：不能携带引用（资料外或工具失败时不应拿无关原文当依据）。
3. 数值有据：答案中的业务数值（阿拉伯数字或中文数字 + 单位，如“30 天”“六十天”“5000 元”）必须出现在
   所引用小节的原文中。用户问题和对话历史里的数值只是待核实的条件，不能作为依据。日期、文档编号、
   条款序号、没有单位的裸数字不在核对范围内。
4. 条件与数值对应：答案中紧挨在某个数值前面的条件（满 / 不满 / 超过 / 不超过 / 至少 + 数值）与该数值配成一对，
   所引用原文中必须有同样的配对（原文中该数值前面的条件包含答案给出的条件）。例如 D07 中 7 天对应的是
   “满 1 年不满 10 年”，所以“满 10 年有 7 天”会被拒；一句话里列出多档（“满 1 年不满 10 年 7 天，满 10 年不满 20 年 12 天”）
   会逐对核对。这只覆盖“条件 + 数值”这一种模式，更一般的语义支撑需要另一个模型评审。

闸门不替模型做业务决策：答案选哪个、是否判为冲突、是否追问，都由模型决定。
不通过时把具体原因作为观察退回给模型修正。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .state import RunState

_WS = re.compile(r"\s+")
MIN_QUOTE_CHARS = 4

_UNITS = r"(个工作日|工作日|个月|天|日|年|周|小时|分钟|万元|元|%|％|人|倍|P)"   # 不含“次”：答案常用它描述工具调用过程
_FACT = re.compile(r"(\d+(?:\.\d+)?)\s*" + _UNITS)
_CN_NUM = re.compile(r"([零〇一二两三四五六七八九十百千]+)\s*(?=" + _UNITS + ")")
_QUALIFIER = re.compile(r"(不满|未满|不超过|超过|满|至少)\s*$")
_CLAUSE = re.compile(r"[\n；;。！!？?]")
# 日期类表达先剔除，避免把“2025 年 1 月 1 日”当成业务数值
_DATES = [
    re.compile(r"\d{4}\s*-\s*\d{1,2}\s*-\s*\d{1,2}"),
    re.compile(r"\d{4}\s*年(\s*\d{1,2}\s*月(\s*\d{1,2}\s*日)?)?"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日"),
]
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _ws(s: str) -> str:
    """只规范化空白：首尾去掉、连续空白合并为一个空格（不删除空格）。"""
    return _WS.sub(" ", s or "").strip()


def _cn_to_int(s: str) -> int | None:
    total, num = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (num or 1) * _CN_UNITS[ch]
            num = 0
        else:
            return None
    return total + num


# “同一天”“哪一天”“每一年”这类说法里的单个“一 / 两”不是数量，不换算
_NOT_QUANTITY_BEFORE = set("同哪某每统唯第这那另任当逐其单")


def _prepare(text: str, originals: dict | None = None) -> str:
    """剔除日期、把中文数字换成阿拉伯数字（仅限后面紧跟单位的情况）。
    originals 用于记录换算前的写法，便于退回信息让模型定位，如 {("1", "天"): "一天"}。"""
    text = (text or "").replace("**", "").replace("\\n", "\n")
    for pat in _DATES:
        text = pat.sub(" ", text)

    def conv(m: re.Match) -> str:
        numeral = m.group(1)
        prev = text[m.start() - 1] if m.start() > 0 else ""
        if len(numeral) == 1 and numeral in "一两" and prev in _NOT_QUANTITY_BEFORE:
            return m.group(0)
        v = _cn_to_int(numeral)
        if v is None:
            return m.group(0)
        if originals is not None:
            unit = _FACT.match(f"{v} " + text[m.end():m.end() + 4])
            if unit:
                originals.setdefault((str(v), unit.group(2)), numeral + unit.group(2))
        return f"{v} "

    return _CN_NUM.sub(conv, text)


def _facts(text: str) -> list[tuple[str, str, str]]:
    """返回 [(限定词, 数值, 单位)]；限定词为空字符串表示普通数值。text 需已经过 _prepare。"""
    out = []
    for m in _FACT.finditer(text):
        num, unit = m.group(1), {"％": "%", "工作日": "个工作日"}.get(m.group(2), m.group(2))
        q = _QUALIFIER.search(text[max(0, m.start() - 4):m.start()])
        qual = {"未满": "不满"}.get(q.group(1), q.group(1)) if q else ""
        out.append((qual, num, unit))
    return out


def _clauses(text: str, originals: dict | None = None) -> list[list[tuple[str, str, str]]]:
    prepared = _prepare(text, originals)
    return [f for f in (_facts(c) for c in _CLAUSE.split(prepared)) if f]


def _pairs(clauses: list[list[tuple[str, str, str]]]) -> list[tuple[frozenset, tuple[str, str]]]:
    """按位置配对：每个普通数值与它前面、上一个普通数值之后的条件配成一对（只返回带条件的配对）。"""
    out = []
    for cl in clauses:
        pending: set = set()
        for q, n, u in cl:
            if q:
                pending.add((q, n, u))
            else:
                if pending:
                    out.append((frozenset(pending), (n, u)))
                pending = set()
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
    gaps = [g for g in (args.get("gaps") or []) if str(g).strip()]
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
    cited_docs = {v["doc_id"] for v in valid}

    # ---- 2. 状态与引用相符 ----
    if status == "answered":
        if not valid:
            problems.append("status=answered 至少需要一条有效引用。")
        elif all(v["doc_status"] == "已废止" for v in valid):
            olds = ",".join(sorted(cited_docs))
            problems.append(f"answered 的依据全部来自已废止文档（{olds}），请查证现行版本后再回答。")
    elif status == "conflict_needs_confirmation":
        if len(cited_docs) < 2:
            problems.append("conflict_needs_confirmation 需要至少两份不同文档的有效引用来展示冲突。")
        if not conflicts:
            problems.append("conflict_needs_confirmation 需要在 conflicts 中描述冲突点。")
        for c in conflicts:
            ids = {str(d).strip().upper() for d in c.get("doc_ids") or []}
            if len(ids) < 2 or not ids <= cited_docs:
                problems.append(f"冲突“{str(c.get('description', ''))[:20]}”涉及的文档 {sorted(ids)} "
                                f"必须至少两份，且都已在 citations 中引用（已引用：{sorted(cited_docs)}）。")
        if not gaps:
            problems.append("conflict_needs_confirmation 需要在 gaps 中说明查证后仍缺少什么信息"
                            "（例如缺少适用范围或优先级说明）。")
    elif status in ("out_of_scope", "tool_error") and citations:
        problems.append(f"status={status} 不应携带引用：资料外或工具失败时不要拿其他原文当依据，请清空 citations。")

    # ---- 3 & 4. 数值有据、条件与数值对应 ----
    if status in ("answered", "conflict_needs_confirmation") and valid:
        cited_refs = sorted({f"{v['doc_id']}#{v['section_id']}" for v in valid})
        source_clauses = [cl for ref in cited_refs for cl in _clauses(state.evidence[ref].text)]
        supported = {(n, u) for cl in source_clauses for _, n, u in cl}
        originals: dict = {}
        answer_clauses = _clauses(answer, originals)

        missing = sorted({(n, u) for cl in answer_clauses for _, n, u in cl} - supported)
        if missing:
            shown = "、".join(f"“{n} {u}”" + (f"（答案中写作“{originals[(n, u)]}”）" if (n, u) in originals else "")
                             for n, u in missing[:5])
            problems.append(f"答案中的数值 {shown} 在所引用的原文中找不到（已引用：{'、'.join(cited_refs)}）。"
                            "用户问题里的数值不能作为依据。请核对结论是否与原文一致，或补充引用能支持该数值的原文。")
        else:
            source_pairs = _pairs(source_clauses)
            for conds, value in _pairs(answer_clauses):
                if not any(v == value and conds <= sc for sc, v in source_pairs):
                    c_txt = "".join(f"{q} {n} {u}" for q, n, u in sorted(conds, key=lambda f: float(f[1])))
                    problems.append(f"答案中“{c_txt}”对应的数值是“{value[0]} {value[1]}”，但所引用的原文中没有这样的对应关系。"
                                    "请核对适用条件与数值的对应关系。")
                    break

    return GateResult(ok=not problems, problems=problems, citations=valid)
