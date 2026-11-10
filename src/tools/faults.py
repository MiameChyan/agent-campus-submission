"""故障注入：模拟检索服务超时/不可用，用于验证“工具失败”验收点。

规格字符串：  "search:1"            search 前 1 次调用失败，之后恢复
              "search:always"       search 始终失败
              "search:always,browse:2"  多个工具用逗号分隔
"""
from __future__ import annotations

from collections import Counter

from .base import ToolExecutionError


class FaultInjector:
    def __init__(self, spec: str | dict | None = None):
        self.rules: dict[str, int | None] = {}   # None 表示 always
        if isinstance(spec, dict):
            items = [f"{k}:{v}" for k, v in spec.items()]
        else:
            items = [s for s in (spec or "").split(",") if s.strip()]
        for item in items:
            name, _, times = item.strip().partition(":")
            times = times.strip() or "1"
            if times == "always":
                self.rules[name.strip()] = None
            elif times.isdigit():
                self.rules[name.strip()] = int(times)
            else:
                raise ValueError(f"无效的故障注入规格：{item!r}（应为 tool:N 或 tool:always）")
        self.calls: Counter = Counter()

    def __bool__(self) -> bool:
        return bool(self.rules)

    def describe(self) -> str:
        return ",".join(f"{k}:{'always' if v is None else v}" for k, v in self.rules.items())

    def check(self, tool_name: str) -> None:
        if tool_name not in self.rules:
            return
        self.calls[tool_name] += 1
        limit = self.rules[tool_name]
        if limit is None or self.calls[tool_name] <= limit:
            raise ToolExecutionError(
                error_type="ServiceUnavailable",
                message=f"{tool_name} 服务暂时不可用（注入故障，第 {self.calls[tool_name]} 次调用）",
                retryable=True,
                suggestion="可重试一次；若仍失败，可改用其他检索/浏览工具，或以 tool_error 状态结束并说明缺口。",
            )
