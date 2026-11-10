"""HTTP API（Mock 模式）：SSE 逐步推送与最终结果。"""
import json

from fastapi.testclient import TestClient

from src.server import app

client = TestClient(app)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_kb_tree():
    tree = client.get("/api/kb/tree").json()
    assert "制度/财务" in tree and {d["doc_id"] for d in tree["制度/财务"]["documents"]} == {"D01", "D02"}
    assert "D02" not in json.dumps(client.get("/api/kb/tree", params={"kb": "no_conflict"}).json()["制度/财务"])


def test_ask_streams_steps_then_final():
    r = client.post("/api/ask", json={"question": "报销期限多久？", "mock": True})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    assert [e for e, _ in events[:-1]] == ["step"] * (len(events) - 1)
    kind, final = events[-1]
    assert kind == "final" and final["status"] == "conflict_needs_confirmation"
    assert len(final["trace"]) == len(events) - 1


def test_ask_with_fault_and_variant():
    final = _parse_sse(client.post("/api/ask", json={"question": "报销期限多久？", "mock": True, "kb": "no_conflict"}).text)[-1][1]
    assert final["status"] == "answered"
    final = _parse_sse(client.post("/api/ask", json={"question": "q", "mock": True, "fail": "search:always"}).text)[-1][1]
    assert final["status"] == "tool_error"


def test_ask_validation():
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "q", "mock": True, "fail": "bad:spec"}).status_code == 400
