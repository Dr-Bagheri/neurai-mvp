import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { useApp } from "../state/AppContext";

export function SettingsPage() {
  const { user, settings, setSettings } = useApp();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    if (next !== confirm) {
      setMessage({ ok: false, text: "تکرار گذرواژهٔ جدید یکسان نیست" });
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setMessage({
        ok: true,
        text: "گذرواژه عوض شد؛ نشست‌های دیگر شما روی همهٔ دستگاه‌ها باطل شدند.",
      });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setMessage({
        ok: false,
        text: err instanceof ApiError ? err.detail : "تغییر گذرواژه ممکن نشد",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card">
        <h3>نمایش</h3>
        <label className="row" style={{ marginBottom: 8 }}>
          <input
            type="checkbox"
            checked={settings.persianDigits}
            onChange={(e) => setSettings({ persianDigits: e.target.checked })}
          />
          نمایش اعداد با ارقام فارسی (۱۲۳ به‌جای 123)
        </label>
        <label className="row">
          <input
            type="checkbox"
            checked={settings.theme === "dark"}
            onChange={(e) => setSettings({ theme: e.target.checked ? "dark" : "light" })}
          />
          پوستهٔ تیره
        </label>
        <p className="muted small" style={{ marginBottom: 0 }}>
          تاریخ‌ها در سراسر برنامه به تقویم شمسی (جلالی) نمایش داده می‌شوند.
        </p>
      </div>

      <div className="card">
        <h3>تغییر گذرواژه</h3>
        <form onSubmit={changePassword} style={{ maxWidth: 360 }}>
          <label className="small muted">گذرواژهٔ فعلی</label>
          <input
            className="input"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            style={{ marginBottom: 10 }}
          />
          <label className="small muted">گذرواژهٔ جدید (حداقل ۶ نویسه)</label>
          <input
            className="input"
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            style={{ marginBottom: 10 }}
          />
          <label className="small muted">تکرار گذرواژهٔ جدید</label>
          <input
            className="input"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            style={{ marginBottom: 12 }}
          />
          {message && (
            <p className={`badge ${message.ok ? "ok" : "danger"}`} style={{ marginBottom: 10 }}>
              {message.text}
            </p>
          )}
          <button
            className="btn primary"
            disabled={busy || !current || next.length < 6 || !confirm}
          >
            {busy ? "در حال ذخیره…" : "تغییر گذرواژه"}
          </button>
        </form>
      </div>

      <div className="card">
        <h3>حساب کاربری</h3>
        <p className="muted small" style={{ marginBottom: 0 }}>
          نام کاربری: <strong className="ltr">{user?.username}</strong> · نام نمایشی:{" "}
          <strong>{user?.display_name}</strong>
          {user?.is_admin && " · مدیر"}
          <br />
          حساب‌ها محلی‌اند و روی سرور دفتر نگهداری می‌شوند؛ هیچ داده‌ای به اینترنت ارسال
          نمی‌شود.
        </p>
      </div>
    </>
  );
}
