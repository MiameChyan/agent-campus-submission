"""LLM 抽象：harness 只依赖这里的结构，真实模型与 Mock 可互换。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMError(Exception):
    """模型接口错误（网络、鉴权、限流、返回格式异常等），harness 据此返回 model_error。"""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str          # 原始 JSON 字符串，由 harness 解析（解析失败也作为观察交给模型）


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    assistant_message: dict          # 原样追加到上下文（含 reasoning_content，DeepSeek 思考模式必须回传）
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""


class LLMClient(Protocol):
    name: str
    mode: str                         # live | offline_mock | scripted

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...
