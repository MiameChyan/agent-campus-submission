import { create } from "zustand";
import { persist } from "zustand/middleware";
import { askStream } from "./api";
import type { Conversation, HistoryItem, Turn } from "./types";

const uid = () => Math.random().toString(36).slice(2, 10);

// 进行中的请求（不持久化）：对话 id → AbortController
const controllers = new Map<string, AbortController>();

interface ChatState {
  conversations: Conversation[];
  mock: boolean;
  setMock: (v: boolean) => void;
  /** 发送问题；conversationId 为空时新建对话，返回对话 id */
  send: (conversationId: string | undefined, question: string) => string;
  stop: (conversationId: string) => void;
  remove: (conversationId: string) => void;
}

/** 把同一对话中已完成的轮次整理成后端需要的 history */
function toHistory(turns: Turn[]): HistoryItem[] {
  return turns
    .filter((t) => t.result && ["answered", "conflict_needs_confirmation", "need_clarification"].includes(t.result.status))
    .map((t) => ({
      question: t.question,
      answer: t.result!.answer || t.result!.clarifying_question || "",
      citations: t.result!.citations.map((c) => ({ doc_id: c.doc_id, section_id: c.section_id })),
    }));
}

export const useChat = create<ChatState>()(
  persist(
    (set, get) => {
      const patchTurn = (cid: string, tid: string, patch: (t: Turn) => Partial<Turn>) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id !== cid
              ? c
              : { ...c, updatedAt: Date.now(), turns: c.turns.map((t) => (t.id === tid ? { ...t, ...patch(t) } : t)) },
          ),
        }));

      return {
        conversations: [],
        mock: false,
        setMock: (mock) => set({ mock }),

        send: (conversationId, question) => {
          const cid = conversationId ?? uid();
          const turn: Turn = { id: uid(), question, steps: [], state: "running", startedAt: Date.now() };
          const existing = get().conversations.find((c) => c.id === cid);
          const history = toHistory(existing?.turns ?? []);
          set((s) => ({
            conversations: existing
              ? s.conversations.map((c) => (c.id === cid ? { ...c, updatedAt: Date.now(), turns: [...c.turns, turn] } : c))
              : [{ id: cid, title: question.slice(0, 30), updatedAt: Date.now(), turns: [turn] }, ...s.conversations],
          }));

          const controller = new AbortController();
          controllers.set(cid, controller);
          askStream({
            question,
            history,
            mock: get().mock,
            signal: controller.signal,
            onStep: (step) => patchTurn(cid, turn.id, (t) => ({ steps: [...t.steps, step] })),
          })
            .then((result) => patchTurn(cid, turn.id, () => ({ result, state: "done", endedAt: Date.now() })))
            .catch((err: Error) =>
              patchTurn(cid, turn.id, () =>
                controller.signal.aborted
                  ? { state: "stopped", endedAt: Date.now() }
                  : { state: "error", error: err.message, endedAt: Date.now() },
              ),
            )
            .finally(() => controllers.delete(cid));
          return cid;
        },

        stop: (cid) => controllers.get(cid)?.abort(),

        remove: (cid) => {
          controllers.get(cid)?.abort();
          set((s) => ({ conversations: s.conversations.filter((c) => c.id !== cid) }));
        },
      };
    },
    {
      name: "kbqa-chat",
      // 刷新页面时，未完成的轮次标记为已停止
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        state.conversations = state.conversations.map((c) => ({
          ...c,
          turns: c.turns.map((t) => (t.state === "running" ? { ...t, state: "stopped" } : t)),
        }));
      },
    },
  ),
);

export const isRunning = (c?: Conversation) => !!c?.turns.some((t) => t.state === "running");
