"""DeepSeek 官方接口（OpenAI 兼容协议）。

- 模型默认 deepseek-flash（DeepSeek-V4.1-Flash），base_url https://api.deepseek.com
- 思考模式通过 extra_body={"thinking": {"type": ...}} 开关；开启时带 tools 的请求必须把
  assistant 消息里的 reasoning_content 原样回传，否则接口返回 400 —— 因此 assistant_message
  保留 reasoning_content，由 harness 追加回上下文。
- 工具 schema 带 strict:true；strict 校验需要 /beta 端点，这里自动切换。
"""
from __future__ import annotations

import time

from openai import APIError, APITimeoutError, OpenAI

from ..config import LLMSettings
from .base import LLMError, LLMResponse, ToolCall


class DeepSeekClient:
    mode = "live"

    def __init__(self, settings: LLMSettings | None = None, strict_tools: bool = True):
        self.settings = settings or LLMSettings.from_env()
        if not self.settings.api_key:
            raise LLMError("未配置 DEEPSEEK_API_KEY：请复制 .env.example 为 .env 并填写，或使用 --mock 离线运行。")
        base_url = self.settings.base_url.rstrip("/")
        if strict_tools and not base_url.endswith("/beta"):
            base_url += "/beta"
        self.client = OpenAI(api_key=self.settings.api_key, base_url=base_url, timeout=self.settings.timeout, max_retries=1)
        self.name = self.settings.model

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        kwargs = dict(model=self.settings.model, messages=messages, tools=tools, tool_choice="auto")
        extra_body = {"thinking": {"type": self.settings.thinking}}
        if self.settings.thinking == "enabled":
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        else:
            kwargs["temperature"] = 0.2
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(**kwargs, extra_body=extra_body)
        except APITimeoutError as exc:
            raise LLMError(f"模型请求超时（{self.settings.timeout}s）：{exc}") from exc
        except APIError as exc:
            raise LLMError(f"模型接口错误：{exc.__class__.__name__}: {exc}") from exc
        except Exception as exc:  # 网络等其他异常
            raise LLMError(f"模型调用失败：{exc.__class__.__name__}: {exc}") from exc
        if not resp.choices:
            raise LLMError("模型返回为空（无 choices）")
        choice = resp.choices[0]
        msg = choice.message
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning is None and getattr(msg, "model_extra", None):
            reasoning = msg.model_extra.get("reasoning_content")
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (msg.tool_calls or [])
        ]
        assistant_message: dict = {"role": "assistant", "content": msg.content or ""}
        if reasoning is not None:
            assistant_message["reasoning_content"] = reasoning
        if tool_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in tool_calls
            ]
        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            assistant_message=assistant_message,
            usage=usage,
            finish_reason=choice.finish_reason or "",
        )
