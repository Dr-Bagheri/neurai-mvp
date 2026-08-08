// The always-available assistant: a persistent panel docked at the PHYSICAL
// LEFT edge (user request) of the RTL app shell, present on every route.
// Collapsible; open by default. The /chat route remains the full archive.
import { Link } from "react-router-dom";
import { useApp } from "../state/AppContext";
import { useChat } from "../state/ChatContext";
import { ChatSurface } from "./ChatSurface";

export function AssistantPanel() {
  const { settings, setSettings } = useApp();
  const { generating } = useChat();
  const open = settings.assistantOpen;

  if (!open) {
    return (
      <aside className="assistant-panel collapsed">
        <button
          className="btn sm"
          title="باز کردن دستیار"
          onClick={() => setSettings({ assistantOpen: true })}
        >
          💬
        </button>
        {generating && <span className="live-dot" title="دستیار در حال پاسخ است" />}
      </aside>
    );
  }

  return (
    <aside className="assistant-panel">
      <div className="assistant-header">
        <div className="row">
          <strong>💬 دستیار</strong>
          {generating && <span className="live-dot" />}
        </div>
        <div className="row">
          <Link to="/chat" className="small" title="نمایش کامل گفتگو">
            بایگانی
          </Link>
          <button
            className="btn sm"
            title="بستن پنل دستیار"
            onClick={() => setSettings({ assistantOpen: false })}
          >
            ⇥
          </button>
        </div>
      </div>
      <div className="assistant-body">
        <ChatSurface compact />
      </div>
    </aside>
  );
}
