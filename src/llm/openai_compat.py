"""通用 OpenAI 兼容客户端：按 ProviderProfile 处理各家差异（见 providers.py）。

已用真实密钥验证：DeepSeek 官方 deepseek-flash（思考模式 + strict 工具 + reasoning_content 回传）。
其他提供方按各自文档配置，只经过单元测试（检查请求参数），未用真实密钥跑评测。
"""
from __future__ import annotations

import copy
import time

from openai import APIError, APITimeoutError, OpenAI

from .base import LLMError, LLMResponse, ToolCall
from .providers import LLMSettings


class OpenAICompatClient:
    mode = "live"

    def __init__(self, settings: LLMSettings, client=None):
        self.settings = settings
        p = settings.provider
        if not settings.api_key and client is None:
            raise LLMError(f"未配置 {p.api_key_env}（或 LLM_API_KEY）：请在 .env 中填写，或使用 --mock 离线运行。")
        if not settings.base_url or not settings.model:
            raise LLMError("提供方 openai_compat 需要设置 LLM_BASE_URL 和 LLM_MODEL。")
        base_url = settings.base_url.rstrip("/")
        if p.strict_tools and p.strict_base_suffix and not base_url.endswith(p.strict_base_suffix):
            base_url += p.strict_base_suffix
        self.client = client or OpenAI(api_key=settings.api_key, base_url=base_url,
                                       timeout=settings.timeout, max_retries=1)
        self.name = settings.model if p.name == "deepseek" else f"{p.name}:{settings.model}"

    # ---------- 请求参数 ----------
    def _tools(self, tools: list[dict]) -> list[dict]:
        if self.settings.provider.strict_tools:
            return tools
        stripped = copy.deepcopy(tools)
        for t in stripped:
            t["function"].pop("strict", None)
        return stripped

    def _messages(self, messages: list[dict]) -> list[dict]:
        if self.settings.provider.echo_reasoning:
            return messages
        # 不需要回传的提供方：去掉 reasoning_content，避免个别服务拒绝未知字段
        return [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]

    def request_kwargs(self, messages: list[dict], tools: list[dict]) -> dict:
        p, s = self.settings.provider, self.settings
        kwargs: dict = dict(model=s.model, messages=self._messages(messages), tools=self._tools(tools), tool_choice="auto")
        thinking_on = s.thinking == "enabled"
        if p.thinking_style == "deepseek":
            kwargs["extra_body"] = {"thinking": {"type": s.thinking}}
        elif p.thinking_style == "enable_thinking":
            kwargs["extra_body"] = {"enable_thinking": thinking_on}
        if thinking_on and p.reasoning_effort:
            kwargs["reasoning_effort"] = s.reasoning_effort
        if not (thinking_on and p.thinking_style != "none"):
            kwargs["temperature"] = 0.2   # 思考模式下各家通常忽略或禁止 temperature
        return kwargs

    # ---------- 调用 ----------
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(**self.request_kwargs(messages, tools))
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
        tool_calls = [ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
                      for tc in (msg.tool_calls or [])]
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
            usage = {"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens,
                     "latency_ms": int((time.perf_counter() - t0) * 1000)}
        return LLMResponse(content=msg.content or "", tool_calls=tool_calls, assistant_message=assistant_message,
                           usage=usage, finish_reason=choice.finish_reason or "")


def create_llm(provider: str | None = None, model: str | None = None) -> OpenAICompatClient:
    try:
        settings = LLMSettings.from_env(provider, model)
    except ValueError as exc:
        raise LLMError(str(exc)) from exc
    return OpenAICompatClient(settings)
