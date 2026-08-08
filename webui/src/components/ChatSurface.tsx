// The assistant conversation UI, rendered by two surfaces: the persistent
// left panel (compact) and the /chat archive page (full). All state lives in
// ChatContext — this component is presentation + input only.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { STOPPED_FA, useChat, type PendingConfirmation } from "../state/ChatContext";

const SUGGESTIONS = [
  "جلسه دیروز رو خلاصه کن",
  "کارهای باز چیه؟",
  "توی جلسه‌ها دنبال «بودجه» بگرد",
  "صورتجلسهٔ آخرین جلسه رو خروجی بگیر",
];

/** Deletion-type skills get explicitly destructive confirmation styling. */
const DESTRUCTIVE_SKILL = /delete|remove|purge|drop/i;

/** Skill-specific Persian explanations for the confirmation card (platform-
 * control skills, D7 amendment). Unknown skills fall back to generic copy. */
const SKILL_EXPLANATION_FA: Record<string, string> = {
  delete_meeting:
    "حذف واقعی جلسه: رونوشت، فایل صوتی، بردارها و نمایهٔ جستجو با هم و برای همیشه پاک می‌شوند و این عمل در گزارش امنیتی ثبت می‌شود.",
  delete_document:
    "سند و نمایهٔ جستجوی آن برای همیشه حذف می‌شوند.",
  set_setting: "یکی از تنظیمات سرور تغییر می‌کند.",
  trigger_backup:
    "یک نسخهٔ پشتیبان رمزشده از پایگاه داده ساخته و به Supabase ارسال می‌شود (Supabase هرگز متن ساده نمی‌بیند).",
};

function ConfirmationCard({
  confirmation,
  onResolve,
}: {
  confirmation: PendingConfirmation;
  onResolve: (approved: boolean) => void;
}) {
  const destructive = DESTRUCTIVE_SKILL.test(confirmation.skill);
  return (
    <div className={"confirm-box" + (destructive ? " destructive" : "")}>
      <strong>{destructive ? "🛑 تأیید عمل حذفی" : "⚠️ نیاز به تأیید شما"}</strong>
      <p className="small" style={{ margin: "6px 0" }}>
        دستیار می‌خواهد مهارت <span className="ltr">{confirmation.skill}</span> را اجرا
        کند (<span className="ltr">{JSON.stringify(confirmation.params)}</span>).{" "}
        {SKILL_EXPLANATION_FA[confirmation.skill] ??
          (destructive ? "این عمل حذفی و بازگشت‌ناپذیر است و در گزارش امنیتی ثبت می‌شود." : "")}{" "}
        عمل‌های دارای اثر جانبی هرگز بدون کلیک شما اجرا نمی‌شوند — حتی اگر متنی در جلسه یا
        سند چنین دستوری داده باشد.
      </p>
      <div className="row">
        <button
          className={"btn sm " + (destructive ? "danger" : "primary")}
          onClick={() => onResolve(true)}
        >
          {destructive ? "بله، حذف کن" : "تأیید و اجرا"}
        </button>
        <button className="btn sm" onClick={() => onResolve(false)}>
          انصراف
        </button>
      </div>
    </div>
  );
}

export function ChatSurface({ compact = false }: { compact?: boolean }) {
  const {
    messages,
    error,
    generating,
    stopping,
    allowCloud,
    setAllowCloud,
    cloudDisabledReason,
    send,
    stop,
    resolveConfirmation,
  } = useChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, generating]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(input);
    setInput("");
  };

  return (
    <div className={"chat-wrap" + (compact ? " compact" : "")}>
      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && !generating && (
          <div className="empty">
            {compact
              ? "دستیار آماده است — بپرسید یا دستور بدهید."
              : "از دستیار بپرسید — «جلسه دیروز رو خلاصه کن»، «کارهای باز چیه؟» یا هر سؤالی از روی جلسه‌ها و اسناد خودتان."}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.key} className={`msg ${m.role}`}>
            {m.stopped ? (
              <div className="bubble" style={{ opacity: 0.75 }}>
                <span className="badge plain">{STOPPED_FA}</span>
              </div>
            ) : (
              <div className="bubble">{m.text}</div>
            )}
            {m.role === "assistant" && !m.stopped && (m.source || m.via || m.fellBack) && (
              <div className="row wrap" style={{ marginTop: 6 }}>
                {m.source && <ProvenanceBadge source={m.source} />}
                {m.via?.startsWith("intent:") && (
                  <span className="skill-chip" title="پاسخ مستقیم مسیریاب قصد (بدون حلقهٔ عامل)">
                    🛠️ <span className="ltr">{m.via.slice("intent:".length)}</span>
                  </span>
                )}
                {m.fellBack && (
                  <span className="badge warn" title="فراخوانی ابری ناموفق بود؛ مدل محلی پاسخ داد">
                    بازگشت به مدل محلی
                  </span>
                )}
              </div>
            )}
            {m.provenance && m.provenance.length > 0 && (
              <div className="citation">
                <strong>📎 منابع مشورت‌شده:</strong>
                <div className="muted small">{m.provenance.join("، ")}</div>
              </div>
            )}
            {m.pendingConfirmation && (
              <ConfirmationCard
                confirmation={m.pendingConfirmation}
                onResolve={(approved) =>
                  void resolveConfirmation(m.key, m.pendingConfirmation!, approved)
                }
              />
            )}
          </div>
        ))}
        {generating && (
          <div className="msg assistant">
            <div className="bubble">
              <span className="typing">
                <i /><i /><i />
              </span>
            </div>
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn danger sm" disabled={stopping} onClick={() => void stop()}>
                {stopping ? "در حال توقف…" : "■ توقف"}
              </button>
            </div>
          </div>
        )}
      </div>

      <div>
        {!compact && (
          <div className="row wrap" style={{ marginBottom: 8 }}>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn sm" disabled={generating} onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {error && (
          <p className="badge danger" style={{ marginBottom: 8 }}>
            {error}
          </p>
        )}
        <form className="row" onSubmit={submit}>
          <input
            className="input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={compact ? "بپرسید یا دستور بدهید…" : "از دستیار بپرسید… مثلاً: «جلسه دیروز رو خلاصه کن»"}
            autoFocus={!compact}
          />
          {generating ? (
            <button
              type="button"
              className="btn danger"
              disabled={stopping}
              onClick={() => void stop()}
            >
              ■{!compact && " توقف"}
            </button>
          ) : (
            <button className="btn primary" disabled={!input.trim()}>
              {compact ? "↵" : "ارسال"}
            </button>
          )}
        </form>
        <label
          className="row small muted"
          style={{ margin: "6px 2px 0", opacity: cloudDisabledReason ? 0.6 : 1 }}
          title={cloudDisabledReason ?? undefined}
        >
          <input
            type="checkbox"
            checked={allowCloud && !cloudDisabledReason}
            disabled={!!cloudDisabledReason}
            onChange={(e) => setAllowCloud(e.target.checked)}
          />
          {compact ? (
            <>مدل ابری {cloudDisabledReason ? `— غیرفعال: ${cloudDisabledReason}` : ""}</>
          ) : (
            <>
              اجازهٔ استفاده از مدل ابری برای این گفتگو
              {cloudDisabledReason
                ? ` — غیرفعال: ${cloudDisabledReason}`
                : " (فقط اگر مدیر برای فضای کاری فعال کرده باشد) — هر پاسخ با نشان 🏠/☁️ مشخص می‌شود."}
            </>
          )}
        </label>
      </div>
    </div>
  );
}
