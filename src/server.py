"""HTTP API（演示入口，前端 frontend/ 调用）。评审主入口仍是 CLI。

    uvicorn src.server:app --port 8000

GET  /api/health          健康检查与当前模型配置
GET  /api/kb/tree         知识库目录与文档列表（只读）
POST /api/ask             提问；以 SSE（text/event-stream）逐步推送 step 事件，最后推送 final 事件
"""
from __future__ import annotations

import json
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import LLMSettings, resolve_kb
from .kb.store import KBValidationError, KnowledgeBase
from .llm.base import LLMError
from .main import build_agent

app = FastAPI(title="企业知识问答 Agent", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class HistoryItem(BaseModel):
    question: str
    answer: str = ""
    citations: list[dict] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[HistoryItem] = Field(default_factory=list)
    mock: bool = False
    kb: str | None = None
    fail: str | None = None
    max_llm_turns: int | None = Field(default=None, ge=1, le=20)
    max_tool_calls: int | None = Field(default=None, ge=1, le=40)


@app.get("/api/health")
def health():
    s = LLMSettings.from_env()
    return {"ok": True, "model": s.model, "api_key_configured": bool(s.api_key), "thinking": s.thinking}


@app.get("/api/kb/tree")
def kb_tree(kb: str | None = None):
    try:
        knowledge = KnowledgeBase.load(resolve_kb(kb))
    except KBValidationError as exc:
        raise HTTPException(400, detail=exc.problems) from exc
    return {path or "/": knowledge.browse(path) for path in sorted(knowledge.dirs)}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/ask")
def ask(req: AskRequest):
    events: queue.Queue = queue.Queue()
    try:
        agent = build_agent(mock=req.mock, kb=req.kb, fail=req.fail, max_llm_turns=req.max_llm_turns,
                            max_tool_calls=req.max_tool_calls, on_event=events.put)
    except (KBValidationError, LLMError, ValueError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    def worker():
        try:
            agent.run(req.question, [h.model_dump() for h in req.history])
        except Exception as exc:  # 兜底：保证前端一定收到结束事件
            events.put({"type": "error", "message": f"{exc.__class__.__name__}: {exc}"})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            if item["type"] == "step":
                yield _sse("step", item["step"])
            elif item["type"] == "final":
                yield _sse("final", item["result"])
            else:
                yield _sse("error", item)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
