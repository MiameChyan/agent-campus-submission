"""一次运行的状态：预算计数、计划、证据台账、错误、闸门退回记录。状态栏据此渲染。"""
from __future__ import annotations

import datetime as _dt
import json
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class EvidenceItem:
    ref: str                 # D01#s3
    doc_id: str
    section_id: str
    title: str
    section_title: str
    version_date: str
    status: str
    scope: str
    supersedes: list[str]
    superseded_by: str | None
    text: str


@dataclass
class RunState:
    max_llm_turns: int
    max_tool_calls: int
    today: str = field(default_factory=lambda: _dt.date.today().isoformat())
    llm_turns: int = 0
    tool_calls: int = 0                          # 业务工具调用次数（计入预算）
    tool_counts: Counter = field(default_factory=Counter)
    plan: list[dict] = field(default_factory=list)
    evidence: dict[str, EvidenceItem] = field(default_factory=dict)   # 已读原文（可引用）
    seen_docs: dict[str, dict] = field(default_factory=dict)          # 检索/浏览/大纲中见过的文档元数据
    call_cache: dict[str, str] = field(default_factory=dict)          # 重复调用检测：签名 → 首次 step
    last_errors: list[str] = field(default_factory=list)
    gate_rejections: int = 0
    budget_blocked: bool = False                 # 预算耗尽后模型仍调用业务工具
    gate_feedback: list[str] = field(default_factory=list)
    usage: Counter = field(default_factory=Counter)
    context_text: str = ""                       # 用户问题与对话历史（闸门核对数值来源时使用）

    @staticmethod
    def signature(name: str, args: dict) -> str:
        clean = {k: v for k, v in args.items() if k != "reason"}
        return name + json.dumps(clean, ensure_ascii=False, sort_keys=True)

    @property
    def tool_budget_left(self) -> int:
        return self.max_tool_calls - self.tool_calls

    @property
    def turns_left(self) -> int:
        return self.max_llm_turns - self.llm_turns
