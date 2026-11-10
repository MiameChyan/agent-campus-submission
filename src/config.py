"""集中读取配置：.env → 环境变量 → 默认值。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = ROOT / "data" / "kb"
KB_VARIANTS = ROOT / "data" / "kb_variants"

load_dotenv(ROOT / ".env", override=False)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    model: str
    thinking: str           # enabled / disabled
    reasoning_effort: str   # low / high / max
    timeout: int

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            thinking=os.getenv("DEEPSEEK_THINKING", "enabled"),
            reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT", "high"),
            timeout=_int("LLM_TIMEOUT", 60),
        )


def default_budget() -> tuple[int, int]:
    return _int("AGENT_MAX_LLM_TURNS", 8), _int("AGENT_MAX_TOOL_CALLS", 12)


def resolve_kb(path_or_variant: str | None) -> Path:
    """--kb 可以是目录路径，也可以是 data/kb_variants 下的变体名（如 no_conflict）。"""
    if not path_or_variant:
        return DEFAULT_KB
    p = Path(path_or_variant)
    if p.is_dir():
        return p
    if (KB_VARIANTS / path_or_variant).is_dir():
        return KB_VARIANTS / path_or_variant
    if (ROOT / p).is_dir():
        return ROOT / p
    return p
