import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ChatMessage, SkillCall } from "../api/types";
import { ProvenanceBadge } from "../components/ProvenanceBadge";

const SUGGESTIONS = [
  "جلسه دیروز رو خلاصه کن",
  "کارهای باز چیه؟",
  "درباره بودجه چی تصمیم گرفتیم؟",
  "صورتجلسه رو خروجی بگیر",
];

function SkillChips({ calls }: { calls: SkillCall[] }) {
  return (
    <div className="row wrap" style={{ marginTop: 8 }}>
      {calls.map((c, i) => (
        <span key={i} className="skill-chip" title={JSON.stringify(c.args)}>
          🛠️ <span className="ltr">{c.skill}</span>
        </span>
      ))}
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => api.chatSeed());
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  let counter = useRef(0);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;
    setInput("");
    setMessages((m) => [
      ...m,
      { id: `u${++counter.current}`, role: "user", text: trimmed },
    ]);
    setThinking(true);
    const reply = await api.sendChat(trimmed);
    setThinking(false);
    setMessages((m) => [...m, reply]);
  };

  const resolveConfirmation = (msgId: string, approved: boolean) => {
    setMessages((m) => {
      const next = m.map((msg) =>
        msg.id === msgId ? { ...msg, pending_confirmation: null } : msg,
      );
      const followup: ChatMessage = approved
        ? {
            id: `c-conf-${msgId}`,
            role: "assistant",
            text: "✅ صورتجلسهٔ رسمی ساخته شد و فایل Word آن در بخش «صورتجلسه و خروجی» همان جلسه در دسترس است. این فراخوانی در گزارش ممیزی ثبت شد.",
            provenance: "local",
            skill_calls: [
              { skill: "export_minutes", args: { format: "Word" }, side_effect: true },
            ],
          }
        : {
            id: `c-conf-${msgId}`,
            role: "assistant",
            text: "باشه، خروجی گرفته نشد. هر وقت خواستید دوباره بگویید.",
            provenance: "local",
          };
      return [...next, followup];
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  return (
    <div className="chat-wrap">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            <div className="bubble">{m.text}</div>
            {m.role === "assistant" && (
              <div className="row wrap" style={{ marginTop: 6 }}>
                {m.provenance && <ProvenanceBadge provenance={m.provenance} />}
              </div>
            )}
            {m.skill_calls && m.skill_calls.length > 0 && <SkillChips calls={m.skill_calls} />}
            {m.citations?.map((c, i) => (
              <div key={i} className="citation">
                <strong>
                  {c.kind === "meeting" ? "📎 از جلسهٔ: " : "📎 از سند: "}
                  {c.kind === "meeting" ? (
                    <Link to={`/meetings/${c.ref_id}`}>{c.title}</Link>
                  ) : (
                    c.title
                  )}
                </strong>
                <div className="muted small">«{c.snippet}»</div>
              </div>
            ))}
            {m.pending_confirmation && (
              <div className="confirm-box">
                <strong>⚠️ نیاز به تأیید شما</strong>
                <p className="small" style={{ margin: "6px 0" }}>
                  دستیار می‌خواهد مهارت{" "}
                  <span className="ltr">{m.pending_confirmation.skill}</span> را اجرا کند (
                  {Object.entries(m.pending_confirmation.args)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join("، ")}
                  ). عمل‌های دارای اثر جانبی هرگز بدون کلیک شما اجرا نمی‌شوند — حتی اگر متنی
                  در جلسه یا سند چنین دستوری داده باشد.
                </p>
                <div className="row">
                  <button
                    className="btn primary sm"
                    onClick={() => resolveConfirmation(m.id, true)}
                  >
                    تأیید و اجرا
                  </button>
                  <button className="btn sm" onClick={() => resolveConfirmation(m.id, false)}>
                    انصراف
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {thinking && (
          <div className="msg assistant">
            <div className="bubble">
              <span className="typing">
                <i /><i /><i />
              </span>
            </div>
          </div>
        )}
      </div>

      <div>
        <div className="row wrap" style={{ marginBottom: 8 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="btn sm" onClick={() => void send(s)}>
              {s}
            </button>
          ))}
        </div>
        <form className="row" onSubmit={submit}>
          <input
            className="input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="از دستیار بپرسید… مثلاً: «جلسه دیروز رو خلاصه کن»"
            autoFocus
          />
          <button className="btn primary" disabled={!input.trim() || thinking}>
            ارسال
          </button>
        </form>
        <p className="muted small" style={{ margin: "6px 2px 0" }}>
          هر پاسخ نشان می‌دهد با مدل محلی 🏠 یا ابری ☁️ ساخته شده و کدام جلسه‌ها/اسناد مشورت
          شده‌اند. دستیار فقط به داده‌هایی دسترسی دارد که خود شما دسترسی دارید.
        </p>
      </div>
    </div>
  );
}
