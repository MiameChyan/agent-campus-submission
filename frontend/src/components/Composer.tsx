import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useChat } from "../store";

interface Props {
  running: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  autoFocus?: boolean;
}

export default function Composer({ running, onSend, onStop, autoFocus }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const mock = useChat((s) => s.mock);
  const setMock = useChat((s) => s.setMock);

  // 高度随内容增长（最多约 8 行）
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const submit = () => {
    const q = text.trim();
    if (!q || running) return;
    onSend(q);
    setText("");
  };

  return (
    <div className="composer">
      <textarea
        ref={ref}
        rows={1}
        value={text}
        autoFocus={autoFocus}
        placeholder="问一个制度或产品问题，Enter 发送，Shift+Enter 换行"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="composer-bar">
        <label className="mock-toggle" title="不调用真实模型，只验证流程">
          <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
          离线 Mock
        </label>
        {running ? (
          <button className="send-btn" onClick={onStop} title="停止" aria-label="停止">
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button className="send-btn" onClick={submit} disabled={!text.trim()} title="发送" aria-label="发送">
            <ArrowUp size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
