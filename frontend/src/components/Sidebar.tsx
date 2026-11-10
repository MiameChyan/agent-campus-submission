import { MessageSquare, PanelLeftClose, PanelLeftOpen, SquarePen, Trash2 } from "lucide-react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useChat } from "../store";

export default function Sidebar({ collapsed, toggle }: { collapsed: boolean; toggle: () => void }) {
  const conversations = useChat((s) => s.conversations);
  const remove = useChat((s) => s.remove);
  const navigate = useNavigate();
  const { id } = useParams();
  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        {!collapsed && <span className="brand">企业知识问答</span>}
        <button className="icon-btn" onClick={toggle} title={collapsed ? "展开侧栏" : "折叠侧栏"} aria-label={collapsed ? "展开侧栏" : "折叠侧栏"}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      <button className="new-chat" onClick={() => navigate("/")} title="新对话">
        <SquarePen size={18} />
        {!collapsed && <span>新对话</span>}
      </button>

      {!collapsed && (
        <nav className="history" aria-label="历史对话">
          {sorted.length === 0 && <p className="history-empty">还没有对话</p>}
          {sorted.map((c) => (
            <NavLink key={c.id} to={`/c/${c.id}`} className="history-item" title={c.title}>
              <MessageSquare size={15} />
              <span className="history-title">{c.title}</span>
              <button
                className="icon-btn danger"
                title="删除对话"
                aria-label="删除对话"
                onClick={(e) => {
                  e.preventDefault();
                  remove(c.id);
                  if (c.id === id) navigate("/");
                }}
              >
                <Trash2 size={14} />
              </button>
            </NavLink>
          ))}
        </nav>
      )}
    </aside>
  );
}
