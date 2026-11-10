import type { HistoryItem, Result, Step } from "./types";

export interface AskOptions {
  question: string;
  history: HistoryItem[];
  mock: boolean;
  signal: AbortSignal;
  onStep: (step: Step) => void;
}

/** POST /api/ask，按 SSE 逐步读取 step 事件，返回最终 final 结果。 */
export async function askStream(opts: AskOptions): Promise<Result> {
  const resp = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: opts.question, history: opts.history, mock: opts.mock }),
    signal: opts.signal,
  });
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => "");
    throw new Error(`请求失败（HTTP ${resp.status}）${text ? "：" + text.slice(0, 200) : ""}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "step") opts.onStep(payload as Step);
      else if (event === "final") return payload as Result;
      else if (event === "error") throw new Error(payload.message || "服务端错误");
    }
  }
  throw new Error("连接已结束，但没有收到最终结果");
}

export async function fetchHealth(): Promise<{ model: string; api_key_configured: boolean }> {
  const resp = await fetch("/api/health");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
