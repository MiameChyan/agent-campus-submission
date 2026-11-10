"""多模型适配：提供方配置解析与各家请求参数差异（不调用真实接口）。"""
from types import SimpleNamespace

import pytest

from src.llm.base import LLMError
from src.llm.openai_compat import OpenAICompatClient, create_llm
from src.llm.providers import PROVIDERS, LLMSettings
from src.tools.registry import CORE_TOOLS

TOOLS = [t.schema() for t in CORE_TOOLS]
MSGS = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "", "reasoning_content": "THINK"}]


def _client(provider, thinking="enabled", **env):
    s = LLMSettings(PROVIDERS[provider], "key", PROVIDERS[provider].base_url or "http://x", "m", thinking, "high", 30)
    return OpenAICompatClient(s, client=object())


def test_default_provider_is_deepseek_and_keeps_legacy_env(monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    s = LLMSettings.from_env()
    assert s.provider.name == "deepseek" and s.api_key == "ds-key" and s.model == "deepseek-flash"


def test_switch_provider_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "moonshot")
    monkeypatch.setenv("MOONSHOT_API_KEY", "ms-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    s = LLMSettings.from_env()
    assert (s.provider.name, s.api_key, s.base_url) == ("moonshot", "ms-key", "https://api.moonshot.cn/v1")
    assert LLMSettings.from_env(model="kimi-x").model == "kimi-x"


def test_deepseek_request_uses_thinking_strict_and_echo():
    c = _client("deepseek")
    kw = c.request_kwargs(MSGS, TOOLS)
    assert kw["extra_body"] == {"thinking": {"type": "enabled"}} and kw["reasoning_effort"] == "high"
    assert "temperature" not in kw
    assert kw["tools"][0]["function"]["strict"] is True
    assert kw["messages"][1]["reasoning_content"] == "THINK"      # 思考模式下必须回传


def test_qwen_style_provider_adapts_parameters():
    kw = _client("siliconflow").request_kwargs(MSGS, TOOLS)
    assert kw["extra_body"] == {"enable_thinking": True} and "reasoning_effort" not in kw
    assert "strict" not in kw["tools"][0]["function"]               # 不支持 strict 时去掉
    assert "reasoning_content" not in kw["messages"][1]              # 不需要回传
    assert TOOLS[0]["function"]["strict"] is True                    # 不修改调用方传入的 schema


def test_provider_without_thinking_uses_temperature():
    kw = _client("moonshot").request_kwargs(MSGS, TOOLS)
    assert "extra_body" not in kw and kw["temperature"] == 0.2


def test_deepseek_strict_switches_to_beta_endpoint():
    s = LLMSettings(PROVIDERS["deepseek"], "k", "https://api.deepseek.com", "deepseek-flash", "enabled", "high", 30)
    assert str(OpenAICompatClient(s).client.base_url).rstrip("/").endswith("/beta")


def test_missing_key_and_unknown_provider(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="DASHSCOPE_API_KEY"):
        create_llm("dashscope")
    with pytest.raises(LLMError, match="未知的模型提供方"):
        create_llm("nope")


def test_response_parsing_keeps_reasoning_for_echo():
    tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="ask_user", arguments='{"question": "?"}'))
    msg = SimpleNamespace(content="", tool_calls=[tc], reasoning_content="R", model_extra={})
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: resp)))
    s = LLMSettings(PROVIDERS["deepseek"], "k", "http://x", "m", "enabled", "high", 30)
    out = OpenAICompatClient(s, client=fake).chat(MSGS, TOOLS)
    assert out.tool_calls[0].name == "ask_user" and out.assistant_message["reasoning_content"] == "R"
    assert out.usage["prompt_tokens"] == 10
