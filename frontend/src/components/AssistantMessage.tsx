import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  ListTodo,
  Loader2,
  MessageCircleQuestion,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation, Status, Step, Turn } from "../types";

const STATUS: Record<Status, { text: string; tone: "ok" | "warn" | "bad" }> = {
  answered: { text: "已回答", tone: "ok" },
  conflict_needs_confirmation: { text: "资料冲突，需要确认", tone: "warn" },
  need_clarification: { text: "需要补充信息", tone: "warn" },
  out_of_scope: { text: "资料范围外", tone: "warn" },
  tool_error: { text: "工具故障", tone: "bad" },
  incomplete: { text: "未完成：达到执行上限", tone: "bad" },
  model_error: { text: "模型调用失败", tone: "bad" },
  cancelled: { text: "已停止", tone: "bad" },
};

/** 把一步 trace 翻译成人能读懂的一行 */
function describe(s: Step): { icon: ReactNode; text: string } {
  const a = s.args as Record<string, string>;
  switch (s.action) {
    case "search":
      return { icon: <Search size={14} />, text: `检索「${a.query}」` };
    case "browse":
      return { icon: <FolderOpen size={14} />, text: `浏览目录 ${a.path || "/"}` };
    case "outline":
      return { icon: <BookOpen size={14} />, text: `查看 ${a.doc_id} 的版本与适用范围` };
    case "read_section":
      return { icon: <FileText size={14} />, text: `阅读原文 ${a.doc_id}#${a.section_id}` };
    case "update_plan":
      return { icon: <ListTodo size={14} />, text: "整理检索计划" };
    case "ask_user":
      return { icon: <MessageCircleQuestion size={14} />, text: "向你追问" };
    case "finish":
      return s.ok
        ? { icon: <Check size={14} />, text: "校验引用并提交回答" }
        : { icon: <ShieldAlert size={14} />, text: "引用校验未通过，退回修改" };
    default:
      return { icon: <AlertTriangle size={14} />, text: s.observation };
  }
}

function Process({ turn }: { turn: Turn }) {
  const running = turn.state === "running";
  const [open, setOpen] = useState(running);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  useEffect(() => {
    setOpen(running); // 运行时展开，结束后自动收起
  }, [running]);

  const seconds = Math.max(1, Math.round(((turn.endedAt ?? now) - turn.startedAt) / 1000));
  const last = turn.steps[turn.steps.length - 1];
  const label = running
    ? last ? `${describe(last).text}…` : "正在思考…"
    : `已检索 ${turn.steps.length} 步 · 用时 ${seconds} 秒`;

  return (
    <div className="process">
      <button className="process-head" onClick={() => setOpen(!open)}>
        {running ? <Loader2 size={14} className="spin" /> : open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>{label}</span>
      </button>
      {open && turn.steps.length > 0 && (
        <ol className="process-steps">
          {turn.steps.map((s) => {
            const d = describe(s);
            return (
              <li key={s.step} className={s.ok ? "" : "failed"}>
                <span className="step-icon">{s.ok ? d.icon : <X size={14} />}</span>
                <div>
                  <div className="step-title">{d.text}</div>
                  <div className="step-obs">{s.observation}</div>
                  {s.reason && <div className="step-reason">依据：{s.reason}</div>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function Citations({ items }: { items: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="citations">
      <div className="section-label">参考资料</div>
      {items.map((c, i) => (
        <div key={i} className={`citation ${open === i ? "open" : ""}`}>
          <button onClick={() => setOpen(open === i ? null : i)}>
            <span className="cite-no">{i + 1}</span>
            <span className="cite-title">
              {c.doc_id}《{c.title}》{c.section_title}
            </span>
            <span className={`cite-meta ${c.doc_status === "已废止" ? "stale" : ""}`}>
              {c.version_date} · {c.doc_status}
            </span>
          </button>
          {open === i && <blockquote>{c.quote}</blockquote>}
        </div>
      ))}
    </div>
  );
}

export default function AssistantMessage({ turn }: { turn: Turn }) {
  const r = turn.result;
  const status = r ? STATUS[r.status] : undefined;
  return (
    <div className="assistant">
      <Process turn={turn} />

      {turn.state === "stopped" && !r && <p className="muted">已停止。</p>}
      {turn.state === "error" && <p className="error-text">{turn.error}</p>}

      {r && (
        <>
          {status && r.status !== "answered" && <span className={`status-chip ${status.tone}`}>{status.text}</span>}
          {r.answer && (
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{r.answer}</ReactMarkdown>
            </div>
          )}
          {r.clarifying_question && <p className="clarify">{r.clarifying_question}</p>}
          {r.conflicts.length > 0 && (
            <div className="callout warn">
              <AlertTriangle size={15} />
              <div>
                {r.conflicts.map((c, i) => (
                  <p key={i}>
                    {c.description}（{c.doc_ids.join("、")}）
                  </p>
                ))}
              </div>
            </div>
          )}
          {r.gaps.length > 0 && (
            <ul className="gaps">
              {r.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          )}
          {r.citations.length > 0 && <Citations items={r.citations} />}
          <div className="meta">
            {r.mode === "offline_mock" ? "离线 Mock" : r.model} · 模型 {r.stats.llm_turns} 轮 · 工具 {r.stats.tool_calls} 次
          </div>
        </>
      )}
    </div>
  );
}
