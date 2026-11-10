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


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def env(*names: str, default: str = "") -> str:
    """按顺序取第一个非空的环境变量。"""
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


@dataclass(frozen=True)
class RetrievalSettings:
    retriever: str              # bm25 | vector | hybrid
    embedding_provider: str     # openai_compat | hash
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    vector_store: str           # memory | milvus
    milvus_uri: str
    milvus_token: str
    milvus_collection: str
    vector_min_score: float
    rrf_k: int

    @classmethod
    def from_env(cls, retriever: str | None = None) -> "RetrievalSettings":
        return cls(
            retriever=retriever or env("RETRIEVER", default="bm25"),
            embedding_provider=env("EMBEDDING_PROVIDER", default="openai_compat"),
            embedding_base_url=env("EMBEDDING_BASE_URL", default="https://api.siliconflow.cn/v1"),
            embedding_api_key=env("EMBEDDING_API_KEY", "SILICONFLOW_API_KEY"),
            embedding_model=env("EMBEDDING_MODEL", default="BAAI/bge-m3"),
            vector_store=env("VECTOR_STORE", default="memory"),
            milvus_uri=env("MILVUS_URI", default="http://localhost:19530"),
            milvus_token=env("MILVUS_TOKEN"),
            milvus_collection=env("MILVUS_COLLECTION", default="kbqa_sections"),
            vector_min_score=_float("VECTOR_MIN_SCORE", 0.0),
            rrf_k=_int("RRF_K", 60),
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
