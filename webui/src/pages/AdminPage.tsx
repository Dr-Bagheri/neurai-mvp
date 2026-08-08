// Server management (v0.3): SETTINGS ONLY — connectivity profile, cloud
// credentials/backup, status/models, users, and the meeting archive. Job
// queue and audit/security logs live on the گزارش‌ها page now. The ASR
// compute dropdown is gone (D13 v0.3: one behavior, no setting).
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type {
  AdminMeetingRow,
  AdminSettings,
  AdminUserRow,
  ConnectivityProfile,
  ModeStatus,
} from "../api/types";
import { ConfidentialBadge, MeetingStatusBadge } from "../components/StatusBadges";
import { formatJalaliShort } from "../lib/jalali";
import { formatTimeOfDay } from "../lib/time";
import { useApp } from "../state/AppContext";
import { useChat } from "../state/ChatContext";

const JOB_LABEL_FA: Record<string, string> = {
  running: "در حال اجرا",
  queued: "در صف",
  done: "تمام شد",
  failed: "ناموفق",
};

function stamp(iso: string, d: (x: string | number) => string): string {
  const date = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  return `${d(formatJalaliShort(date))} — ${d(formatTimeOfDay(date))}`;
}

/** Typed destructive confirmation (D12-logged action behind it). */
function RemoveMeetingModal({
  meeting,
  onCancel,
  onConfirm,
}: {
  meeting: AdminMeetingRow;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const match = typed.trim() === "حذف";
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>حذف کامل جلسه</h3>
        <p className="small">
          جلسهٔ <strong>«{meeting.title}»</strong> (متعلق به{" "}
          <span className="ltr">{meeting.owner}</span>) برای همیشه حذف می‌شود: رونوشت، صدا،
          بردارها و نمایهٔ جستجو با هم. این عمل بازگشت‌پذیر نیست و در گزارش امنیتی
          (زنجیرهٔ ممیزی) ثبت می‌شود.
        </p>
        <label className="small muted">برای تأیید، عبارت «حذف» را تایپ کنید:</label>
        <input
          className="input"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoFocus
          style={{ margin: "6px 0 14px" }}
        />
        <div className="row">
          <button className="btn danger" disabled={!match} onClick={onConfirm}>
            حذف برای همیشه
          </button>
          <button className="btn" onClick={onCancel}>
            انصراف
          </button>
        </div>
      </div>
    </div>
  );
}

export function AdminPage() {
  const { d, adminStatus, refreshAdminStatus } = useApp();
  const { mutationCounter } = useChat();
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [archive, setArchive] = useState<AdminMeetingRow[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState<AdminMeetingRow | null>(null);

  const [modeStatus, setModeStatus] = useState<ModeStatus | null>(null);

  // secret inputs (write-only — the server never returns values)
  const [orKey, setOrKey] = useState("");
  const [sbUrl, setSbUrl] = useState("");
  const [sbKey, setSbKey] = useState("");
  const [asrUrl, setAsrUrl] = useState("");
  const [asrKey, setAsrKey] = useState("");

  // new-user form
  const [nu, setNu] = useState({ username: "", password: "", display_name: "" });
  const [nuMessage, setNuMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [s, u, arch, mode] = await Promise.all([
        api.adminSettings(),
        api.adminUsers(),
        api.adminAllMeetings(),
        api.getMode(),
      ]);
      setSettings(s);
      setUsers(u);
      setArchive(arch);
      setModeStatus(mode);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "خطا در بارگذاری");
    }
  }, []);

  // mutationCounter: reload after the assistant performs a confirmed
  // side-effectful skill so this view shows the result.
  useEffect(() => {
    void refreshAdminStatus();
    void loadAll();
  }, [refreshAdminStatus, loadAll, mutationCounter]);

  const patchSettings = async (patch: Parameters<typeof api.updateAdminSettings>[0]) => {
    setError("");
    try {
      setSettings(await api.updateAdminSettings(patch));
      await refreshAdminStatus();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "ذخیرهٔ تنظیمات ممکن نشد");
    }
  };

  const switchMode = async (mode: "offline" | "online") => {
    setError("");
    setNotice("");
    try {
      setModeStatus(await api.setMode(mode));
      setSettings(await api.adminSettings());
      await refreshAdminStatus();
      setNotice(mode === "online" ? "سرور آنلاین شد." : "سرور به حالت آفلاین رفت.");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "تغییر حالت ممکن نشد");
    }
  };

  const removeMeeting = async (meeting: AdminMeetingRow) => {
    setRemoving(null);
    setError("");
    try {
      await api.adminRemoveMeeting(meeting.id);
      setNotice(`جلسهٔ «${meeting.title}» حذف شد و در گزارش امنیتی ثبت شد.`);
      await loadAll();
      await refreshAdminStatus();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "حذف ممکن نشد");
    }
  };

  const backupNow = async () => {
    setError("");
    setNotice("");
    try {
      const { job_id } = await api.backupNow();
      setNotice(
        `پشتیبان‌گیری در صف قرار گرفت (کار ${d(job_id)}) — وضعیت آن در «گزارش‌ها» قابل پیگیری است.`,
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "پشتیبان‌گیری ممکن نشد");
    }
  };

  const createUser = async (e: FormEvent) => {
    e.preventDefault();
    setNuMessage(null);
    try {
      await api.createUser(nu.username.trim(), nu.password, nu.display_name.trim());
      setUsers(await api.adminUsers());
      setNu({ username: "", password: "", display_name: "" });
      setNuMessage({ ok: true, text: "کاربر ساخته شد." });
    } catch (err) {
      setNuMessage({
        ok: false,
        text: err instanceof ApiError ? err.detail : "ساخت کاربر ممکن نشد",
      });
    }
  };

  if (error && !settings) return <p className="badge danger">{error}</p>;
  if (!settings) return <p className="muted">در حال بارگذاری…</p>;

  const airGapped = settings.connectivity_profile === "air_gapped";
  const backupDisabledReason = airGapped
    ? "در پروفایل ایزوله هیچ مسیر ابری فعال نیست"
    : !settings.supabase_configured
      ? "ابتدا نشانی و کلید Supabase را در «اعتبارنامه‌های ابری» تنظیم کنید"
      : null;

  return (
    <>
      {(error || notice) && (
        <p className={`badge ${error ? "danger" : "ok"}`} style={{ marginBottom: 12 }}>
          {error || notice}
        </p>
      )}

      <div className="grid-2">
        <div className="card">
          <h3>پروفایل اتصال سرور</h3>
          <p className="muted small">
            «ایزوله» تمام مسیرهای ابری را در سطح کد غیرفعال می‌کند — نه پروب شبکه، نه
            تله‌متری. «خودکار» فقط با رضایتِ فضای کاری از ابر استفاده می‌کند و هنگام قطع
            شبکه بی‌صدا به مدل محلی برمی‌گردد.
          </p>
          <div className="row wrap" style={{ marginBottom: 12 }}>
            {(["auto", "air_gapped"] as ConnectivityProfile[]).map((p) => (
              <button
                key={p}
                className={"btn" + (settings.connectivity_profile === p ? " primary" : "")}
                onClick={() => void patchSettings({ connectivity_profile: p })}
              >
                {p === "auto" ? "🌐 خودکار" : "⛔ ایزوله (Air-gapped)"}
              </button>
            ))}
          </div>
          <h3 style={{ marginTop: 16 }}>حالت سرور (D15)</h3>
          <p className="muted small">
            یک کلید واحد: در حالت «آفلاین» هیچ کار ابری انجام نمی‌شود؛ «آنلاین» مسیرهای
            ابریِ دارای رضایت را باز می‌کند و فقط وقتی ممکن است که اینترنت واقعاً در دسترس
            باشد.
          </p>
          <div className="row wrap">
            <button
              className={"btn" + (modeStatus?.mode === "offline" ? " primary" : "")}
              onClick={() => void switchMode("offline")}
            >
              🔌 آفلاین
            </button>
            <button
              className={"btn" + (modeStatus?.mode === "online" ? " primary" : "")}
              disabled={!modeStatus?.online_available}
              style={{ opacity: modeStatus?.online_available ? 1 : 0.55 }}
              title={
                airGapped
                  ? "در پروفایل ایزوله، حالت آنلاین وجود ندارد"
                  : modeStatus?.online_available
                    ? undefined
                    : "اینترنت در دسترس نیست"
              }
              onClick={() => void switchMode("online")}
            >
              🌐 آنلاین
            </button>
            {!modeStatus?.online_available && (
              <span className="muted small">
                {airGapped ? "ایزوله — آنلاین وجود ندارد" : "غیرفعال: اینترنت در دسترس نیست"}
              </span>
            )}
          </div>
          <p className="muted small" style={{ margin: "10px 0 0" }}>
            پردازش گفتار خودکار است: روی GPU اجرا می‌شود و در صورت هر خطا بی‌صدا به CPU
            برمی‌گردد — تنظیمی ندارد (D13). رونویسی ابری فقط با رضایت صریحِ هر جلسه (D15).
          </p>
        </div>

        <div className="card">
          <h3>اعتبارنامه‌های ابری</h3>
          <p className="muted small">
            مقادیر فقط نوشته می‌شوند و در مخزن امن (DPAPI) نگه داشته می‌شوند — سرور هرگز
            آن‌ها را برنمی‌گرداند. برای پاک کردن، فیلد را خالی ذخیره کنید.
          </p>
          <label className="small muted">
            کلید OpenRouter — {settings.openrouter_key_set ? "✅ تنظیم شده" : "تنظیم نشده"}
          </label>
          <div className="row" style={{ margin: "4px 0 10px" }}>
            <input
              className="input ltr"
              type="password"
              placeholder="sk-or-…"
              value={orKey}
              onChange={(e) => setOrKey(e.target.value)}
              autoComplete="off"
            />
            <button
              className="btn sm"
              onClick={() => {
                void patchSettings({ openrouter_key: orKey });
                setOrKey("");
              }}
            >
              ذخیره
            </button>
            {settings.openrouter_key_set && (
              <button
                className="btn danger sm"
                onClick={() => void patchSettings({ openrouter_key: "" })}
              >
                پاک کردن
              </button>
            )}
          </div>

          <label className="small muted">
            Supabase (پشتیبان‌گیری) — {settings.supabase_configured ? "✅ تنظیم شده" : "تنظیم نشده"}
          </label>
          <div className="row" style={{ margin: "4px 0 6px" }}>
            <input
              className="input ltr"
              placeholder="https://xyz.supabase.co"
              value={sbUrl}
              onChange={(e) => setSbUrl(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="row" style={{ marginBottom: 10 }}>
            <input
              className="input ltr"
              type="password"
              placeholder="service key"
              value={sbKey}
              onChange={(e) => setSbKey(e.target.value)}
              autoComplete="off"
            />
            <button
              className="btn sm"
              disabled={!sbUrl.trim() || !sbKey.trim()}
              onClick={() => {
                void patchSettings({ supabase_url: sbUrl.trim(), supabase_key: sbKey.trim() });
                setSbUrl("");
                setSbKey("");
              }}
            >
              ذخیره
            </button>
            {settings.supabase_configured && (
              <button
                className="btn danger sm"
                onClick={() => void patchSettings({ supabase_url: "", supabase_key: "" })}
              >
                پاک کردن
              </button>
            )}
          </div>

          <label className="small muted">
            سرویس رونویسی ابری (D15) —{" "}
            {settings.cloud_asr_configured ? "✅ تنظیم شده" : "تنظیم نشده"}
          </label>
          <div className="row" style={{ margin: "4px 0 6px" }}>
            <input
              className="input ltr"
              placeholder="https://api.groq.com/openai/v1"
              value={asrUrl}
              onChange={(e) => setAsrUrl(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="row" style={{ marginBottom: 10 }}>
            <input
              className="input ltr"
              type="password"
              placeholder="API key"
              value={asrKey}
              onChange={(e) => setAsrKey(e.target.value)}
              autoComplete="off"
            />
            <button
              className="btn sm"
              disabled={!asrUrl.trim() || !asrKey.trim()}
              onClick={() => {
                void patchSettings({ cloud_asr_url: asrUrl.trim(), cloud_asr_key: asrKey.trim() });
                setAsrUrl("");
                setAsrKey("");
              }}
            >
              ذخیره
            </button>
            {settings.cloud_asr_configured && (
              <button
                className="btn danger sm"
                onClick={() => void patchSettings({ cloud_asr_url: "", cloud_asr_key: "" })}
              >
                پاک کردن
              </button>
            )}
          </div>

          <div className="row" title={backupDisabledReason ?? undefined}>
            <button
              className="btn primary"
              disabled={!!backupDisabledReason}
              style={{ opacity: backupDisabledReason ? 0.55 : 1 }}
              onClick={() => void backupNow()}
            >
              ☁️ پشتیبان‌گیری ابری — همین حالا
            </button>
            {backupDisabledReason && (
              <span className="muted small">غیرفعال: {backupDisabledReason}</span>
            )}
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>
            پایگاه داده به‌صورت رمزشده (کلید فقط روی همین سرور) بارگذاری می‌شود؛ Supabase
            هرگز متن ساده نمی‌بیند (D4).
          </p>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>وضعیت سرور</h3>
          {adminStatus && (
            <>
              <div className="row wrap" style={{ marginBottom: 10 }}>
                {adminStatus.live_meeting_active ? (
                  <span className="badge danger">● جلسه‌ای در حال ضبط است</span>
                ) : (
                  <span className="badge ok">آماده — جلسهٔ زنده‌ای در جریان نیست</span>
                )}
                <span className="badge plain">{d(adminStatus.users)} کاربر</span>
                <span className="badge plain">{d(adminStatus.meetings)} جلسه</span>
                <span className="badge plain">
                  OpenRouter: {adminStatus.openrouter_configured ? "✅" : "—"} · Supabase:{" "}
                  {adminStatus.supabase_configured ? "✅" : "—"}
                </span>
              </div>
              <p className="muted small">
                صف کارها:{" "}
                {Object.entries(adminStatus.jobs).length === 0
                  ? "خالی"
                  : Object.entries(adminStatus.jobs)
                      .map(([st, n]) => `${JOB_LABEL_FA[st] ?? st}: ${d(n)}`)
                      .join(" · ")}{" "}
                — جزئیات در «گزارش‌ها»
              </p>
            </>
          )}
          <h3 style={{ marginTop: 14 }}>مدل‌ها</h3>
          <table className="table">
            <tbody>
              <tr>
                <td className="muted">مدل زبانی محلی</td>
                <td className="ltr">{settings.local_chat_model}</td>
              </tr>
              <tr>
                <td className="muted">مدل ابری گفتگو (با رضایت)</td>
                <td className="ltr">{settings.cloud_chat_model}</td>
              </tr>
              <tr>
                <td className="muted">مدل ابری سنگین (خلاصه/صورتجلسه)</td>
                <td className="ltr">{settings.cloud_heavy_model}</td>
              </tr>
              <tr>
                <td className="muted">مدل رونویسی ابری (D15)</td>
                <td className="ltr">{settings.cloud_asr_model}</td>
              </tr>
              <tr>
                <td className="muted">مدل بردارسازی</td>
                <td className="ltr">{settings.embed_model}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>کاربران</h3>
          <table className="table">
            <thead>
              <tr>
                <th>نام کاربری</th>
                <th>نام نمایشی</th>
                <th>نقش</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="ltr">{u.username}</td>
                  <td>{u.display_name}</td>
                  <td>{u.is_admin ? <span className="badge warn">مدیر</span> : "کاربر"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form onSubmit={createUser} style={{ marginTop: 12 }}>
            <div className="row wrap">
              <input
                className="input"
                style={{ maxWidth: 140 }}
                placeholder="نام کاربری"
                value={nu.username}
                onChange={(e) => setNu({ ...nu, username: e.target.value })}
              />
              <input
                className="input"
                style={{ maxWidth: 140 }}
                placeholder="نام نمایشی"
                value={nu.display_name}
                onChange={(e) => setNu({ ...nu, display_name: e.target.value })}
              />
              <input
                className="input"
                style={{ maxWidth: 140 }}
                type="password"
                placeholder="گذرواژه"
                value={nu.password}
                onChange={(e) => setNu({ ...nu, password: e.target.value })}
              />
              <button
                className="btn primary sm"
                disabled={!nu.username.trim() || nu.password.length < 6}
              >
                ＋ کاربر جدید
              </button>
            </div>
            {nuMessage && (
              <p className={`badge ${nuMessage.ok ? "ok" : "danger"}`} style={{ marginTop: 8 }}>
                {nuMessage.text}
              </p>
            )}
          </form>
        </div>
      </div>

      <div className="card">
        <h3>بایگانی جلسه‌ها (همهٔ کاربران)</h3>
        <p className="muted small">
          حذف از اینجا «حذف واقعی» است (رونوشت + صدا + بردارها + نمایه) و همیشه در گزارش
          امنیتی ثبت می‌شود.
        </p>
        {archive.length === 0 ? (
          <div className="empty">جلسه‌ای در بایگانی نیست.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>عنوان</th>
                <th>مالک</th>
                <th>تاریخ</th>
                <th>وضعیت</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {archive.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.title} <ConfidentialBadge sensitivity={m.sensitivity} />
                  </td>
                  <td className="ltr">{m.owner}</td>
                  <td className="muted small">{stamp(m.started_at ?? m.created_at, d)}</td>
                  <td>
                    <MeetingStatusBadge status={m.status} />
                  </td>
                  <td>
                    <button className="btn danger sm" onClick={() => setRemoving(m)}>
                      حذف
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {removing && (
        <RemoveMeetingModal
          meeting={removing}
          onCancel={() => setRemoving(null)}
          onConfirm={() => void removeMeeting(removing)}
        />
      )}
    </>
  );
}
