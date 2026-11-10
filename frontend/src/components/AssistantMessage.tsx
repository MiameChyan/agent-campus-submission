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

const ICONS: Record<string, ReactNode> = {
  search: <Search size={14} />,
  browse: <FolderOpen size={14} />,
  outline: <BookOpen size={14} />,
  read_section: <FileText size={14} />,
  update_plan: <ListTodo size={14} />,
  ask_user: <MessageCircleQuestion size={14} />,
  finish: <Check size={14} />,
};

/** 同一动作的多次调用合并成一句话，如“阅读原文 D01#s3、D02#s1” */
function describeAction(action: string, steps: Step[]): string {
  const args = steps.map((s) => s.args as Record<string, string>);
  const list = (f: (a: Record<string, string>) => string) => args.map(f).join("、");
  switch (action) {
    case "search":
      return `检索${args.map((a) => `「${a.query}」`).join("")}`;
    case "browse":
      return `浏览目录 ${list((a) => a.path || "/")}`;
    case "outline":
      return `查看 ${list((a) => a.doc_id)} 的版本与适用范围`;
    case "read_section":
      return `阅读原文 ${list((a) => `${a.doc_id}#${a.section_id}`)}`;
    case "update_plan":
      return "整理检索计划";
    case "ask_user":
      return "向你追问";
    case "finish":
      return steps.every((s) => s.ok) ? "校验引用并提交回答" : "引用校验未通过，退回修改";
    default:
      return steps.map((s) => s.observation).join("；");
  }
}

interface Round {
  turn: number;
  steps: Step[];
  title: string;
  icon: ReactNode;
  failed: boolean;
  reasons: string[];
}

/** 按模型轮次分组：同一轮里并行发出的调用合并为一条 */
function toRounds(steps: Step[]): Round[] {
  const rounds: Round[] = [];
  for (const s of steps) {
    const last = rounds[rounds.length - 1];
    if (last && last.turn === s.turn) last.steps.push(s);
    else rounds.push({ turn: s.turn, steps: [s], title: "", icon: null, failed: false, reasons: [] });
  }
  for (const r of rounds) {
    const actions = [...new Set(r.steps.map((s) => s.action))];
    r.title = actions.map((a) => describeAction(a, r.steps.filter((s) => s.action === a))).join(" · ");
    r.failed = r.steps.some((s) => !s.ok);
    r.icon = r.failed && r.steps.every((s) => !s.ok) ? <X size={14} /> : ICONS[actions[0]] ?? <AlertTriangle size={14} />;
    if (actions[0] === "finish" && r.failed) r.icon = <ShieldAlert size={14} />;
    r.reasons = [...new Set(r.steps.map((s) => s.reason).filter(Boolean))];
  }
  return rounds;
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
  const rounds = toRounds(turn.steps);
  const last = rounds[rounds.length - 1];
  const label = running
    ? last ? `${last.title}…` : "正在思考…"
    : `已检索 ${rounds.length} 轮 · 调用工具 ${turn.steps.length} 次 · 用时 ${seconds} 秒`;

  return (
    <div className="process">
      <button className="process-head" onClick={() => setOpen(!open)}>
        {running ? <Loader2 size={14} className="spin" /> : open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>{label}</span>
      </button>
      {open && rounds.length > 0 && (
        <ol className="process-steps">
          {rounds.map((r) => (
            <li key={r.steps[0].step} className={r.failed ? "failed" : ""}>
              <span className="step-icon">{r.icon}</span>
              <div>
                <div className="step-title">
                  {r.title}
                  {r.steps.length > 1 && <span className="parallel-tag">并行 {r.steps.length} 项</span>}
                </div>
                {r.steps.length === 1 ? (
                  <div className="step-obs">{r.steps[0].observation}</div>
                ) : (
                  <ul className="step-obs-list">
                    {r.steps.map((s) => (
                      <li key={s.step} className={s.ok ? "" : "failed"}>
                        {s.observation}
                      </li>
                    ))}
                  </ul>
                )}
                {r.reasons.length > 0 && <div className="step-reason">依据：{r.reasons.join("；")}</div>}
              </div>
            </li>
          ))}
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
