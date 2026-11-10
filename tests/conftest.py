import shutil
from pathlib import Path

import pytest

from src.agent.harness import Agent
from src.config import DEFAULT_KB
from src.kb.store import KnowledgeBase
from src.tools.faults import FaultInjector


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load(DEFAULT_KB)


@pytest.fixture
def kb_copy(tmp_path) -> Path:
    """可随意修改的知识库副本。"""
    dst = tmp_path / "kb"
    shutil.copytree(DEFAULT_KB, dst)
    return dst


@pytest.fixture
def make_agent(kb):
    def _make(llm, **kw):
        fail = kw.pop("fail", None)
        return Agent(llm, kw.pop("knowledge", kb), faults=FaultInjector(fail), **kw)
    return _make
