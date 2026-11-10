"""工具定义与执行结果的公共结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

REASON_PROP = {
    "type": "string",
    "description": "一句话说明为什么选择这个动作（会记录到运行轨迹，作为简要决策依据）",
}


class ToolExecutionError(Exception):
    """工具执行失败。retryable/suggestion 会原样交给模型，由模型决定下一步（代码不自动重试）。"""

    def __init__(self, error_type: str, message: str, retryable: bool, suggestion: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.retryable = retryable
        self.suggestion = suggestion

    def to_observation(self) -> dict:
        return {
            "ok": False,
            "error_type": self.error_type,
            "message": self.message,
            "retryable": self.retryable,
            "suggestion": self.suggestion,
        }


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    kind: str                                   # business | control | terminal
    handler: Callable[..., Any] | None = None   # terminal 工具由 harness 处理
    required: list[str] = field(default_factory=list)

    def schema(self) -> dict:
        props = {**self.properties, "reason": REASON_PROP}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    # strict 模式要求所有属性都在 required 中
                    "required": list(props.keys()),
                    "additionalProperties": False,
                },
            },
        }
