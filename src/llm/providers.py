"""模型提供方配置：各家 OpenAI 兼容接口的差异集中在这里，Agent 代码不感知具体厂商。

差异点：
  thinking_style      思考模式的开关方式：deepseek（extra_body.thinking）/ enable_thinking（Qwen 系）/ none
  echo_reasoning      带工具的多轮请求是否必须原样回传 reasoning_content（DeepSeek 思考模式必须，否则 400）
  strict_tools        是否支持工具参数 strict 校验；不支持时发送前去掉 schema 中的 strict 字段
  strict_base_suffix  strict 需要切换的端点后缀（DeepSeek 为 /beta）
  reasoning_effort    是否接受 reasoning_effort 参数

新增一家：在 PROVIDERS 中加一条 ProviderProfile；只要是 OpenAI 兼容协议，不需要写新代码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..config import env


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    thinking_style: str = "none"          # deepseek | enable_thinking | none
    echo_reasoning: bool = False
    strict_tools: bool = False
    strict_base_suffix: str = ""
    reasoning_effort: bool = False
    verified: bool = False                 # 是否用真实密钥跑通过本项目的评测


PROVIDERS: dict[str, ProviderProfile] = {
    "deepseek": ProviderProfile(
        name="deepseek", base_url="https://api.deepseek.com", api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-flash", thinking_style="deepseek", echo_reasoning=True,
        strict_tools=True, strict_base_suffix="/beta", reasoning_effort=True, verified=True,
    ),
    "siliconflow": ProviderProfile(
        name="siliconflow", base_url="https://api.siliconflow.cn/v1", api_key_env="SILICONFLOW_API_KEY",
        default_model="Qwen/Qwen3-32B", thinking_style="enable_thinking",
    ),
    "dashscope": ProviderProfile(
        name="dashscope", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY", default_model="qwen-plus", thinking_style="enable_thinking",
    ),
    "moonshot": ProviderProfile(
        name="moonshot", base_url="https://api.moonshot.cn/v1", api_key_env="MOONSHOT_API_KEY",
        default_model="kimi-k2-0905-preview",
    ),
    "openai": ProviderProfile(
        name="openai", base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY",
        default_model="gpt-4.1-mini", strict_tools=True,
    ),
    # 任意 OpenAI 兼容服务：用 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 指定
    "openai_compat": ProviderProfile(
        name="openai_compat", base_url="", api_key_env="LLM_API_KEY", default_model="",
    ),
}


@dataclass(frozen=True)
class LLMSettings:
    provider: ProviderProfile
    api_key: str
    base_url: str
    model: str
    thinking: str           # enabled / disabled（提供方不支持时忽略）
    reasoning_effort: str   # low / high / max（提供方不支持时忽略）
    timeout: int

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None) -> "LLMSettings":
        name = provider or env("LLM_PROVIDER", default="deepseek")
        if name not in PROVIDERS:
            raise ValueError(f"未知的模型提供方 {name!r}，可选：{', '.join(PROVIDERS)}")
        p = PROVIDERS[name]
        is_ds = name == "deepseek"
        try:
            timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        except ValueError:
            timeout = 60
        return cls(
            provider=p,
            api_key=env("LLM_API_KEY", p.api_key_env),
            # 兼容早期只支持 DeepSeek 时的 DEEPSEEK_* 变量
            base_url=env("LLM_BASE_URL", *(["DEEPSEEK_BASE_URL"] if is_ds else []), default=p.base_url),
            model=model or env("LLM_MODEL", *(["DEEPSEEK_MODEL"] if is_ds else []), default=p.default_model),
            thinking=env("LLM_THINKING", "DEEPSEEK_THINKING", default="enabled"),
            reasoning_effort=env("LLM_REASONING_EFFORT", "DEEPSEEK_REASONING_EFFORT", default="high"),
            timeout=timeout,
        )
