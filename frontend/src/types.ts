// 与后端 src/agent/harness.py 的输出结构保持一致

export type Status =
  | "answered"
  | "conflict_needs_confirmation"
  | "out_of_scope"
  | "need_clarification"
  | "tool_error"
  | "incomplete"
  | "model_error"
  | "cancelled";

export interface Step {
  step: number;
  turn: number;
  action: string;
  args: Record<string, unknown>;
  observation: string;
  reason: string;
  ok: boolean;
}

export interface Citation {
  doc_id: string;
  section_id: string;
  title: string;
  section_title: string;
  version_date: string;
  doc_status: string;
  quote: string;
}

export interface Result {
  question: string;
  status: Status;
  incomplete_reason: string | null;
  mode: string;
  model: string;
  answer: string;
  citations: Citation[];
  conflicts: { description: string; doc_ids: string[] }[];
  gaps: string[];
  clarifying_question: string | null;
  stats: { llm_turns: number; tool_calls: number; elapsed_ms: number };
  trace: Step[];
}

/** 一问一答 */
export interface Turn {
  id: string;
  question: string;
  steps: Step[];
  result?: Result;
  error?: string;
  state: "running" | "done" | "stopped" | "error";
  startedAt: number;
  endedAt?: number;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: number;
  turns: Turn[];
}

export interface HistoryItem {
  question: string;
  answer: string;
  citations: { doc_id: string; section_id: string }[];
}
