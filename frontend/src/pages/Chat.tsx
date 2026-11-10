import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchHealth } from "../api";
import AssistantMessage from "../components/AssistantMessage";
import Composer from "../components/Composer";
import { isRunning, useChat } from "../store";

const EXAMPLES = ["报销期限多久？", "按现行制度，年假有几天？", "我每周可以远程办公几天？", "星剪 App 免费版导出有水印吗？"];

export default function Chat() {
  const { id } = useParams();
  const navigate = useNavigate();
  const conversation = useChat((s) => s.conversations.find((c) => c.id === id));
  const send = useChat((s) => s.send);
  const stop = useChat((s) => s.stop);
  const mock = useChat((s) => s.mock);
  const running = isRunning(conversation);
  const bottom = useRef<HTMLDivElement>(null);
  const [notice, setNotice] = useState("");

  const lastSteps = conversation?.turns.at(-1)?.steps.length ?? 0;
  // 新版浏览器的 scrollIntoView 会返回 Promise，effect 不能把它返回出去
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation?.turns.length, lastSteps]);

  useEffect(() => {
    fetchHealth()
      .then((h) => setNotice(h.api_key_configured ? "" : "后端未配置 DEEPSEEK_API_KEY，可勾选“离线 Mock”体验流程。"))
      .catch(() => setNotice("无法连接后端，请先运行 uvicorn src.server:app --port 8000"));
  }, []);

  // 对话不存在（如被删除）时回到新对话
  useEffect(() => {
    if (id && !conversation) navigate("/", { replace: true });
  }, [id, conversation, navigate]);

  const onSend = (q: string) => {
    const cid = send(id, q);
    if (!id) navigate(`/c/${cid}`);
  };

  const composer = (
    <Composer running={running} onSend={onSend} onStop={() => id && stop(id)} autoFocus />
  );

  if (!conversation) {
    return (
      <div className="chat empty-state">
        <h1>有什么制度或产品问题？</h1>
        <p className="muted">回答都附带文档出处；资料冲突或缺失时会直接告诉你。</p>
        {notice && !mock && <p className="notice">{notice}</p>}
        <div className="composer-wrap">{composer}</div>
        <div className="examples">
          {EXAMPLES.map((q) => (
            <button key={q} onClick={() => onSend(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="chat">
      <div className="messages">
        {conversation.turns.map((t) => (
          <div key={t.id} className="turn">
            <div className="user-row">
              <div className="user-bubble">{t.question}</div>
            </div>
            <AssistantMessage turn={t} />
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <div className="composer-dock">
        {notice && !mock && <p className="notice">{notice}</p>}
        {composer}
        <p className="disclaimer">资料为合成数据，仅用于演示。</p>
      </div>
    </div>
  );
}
