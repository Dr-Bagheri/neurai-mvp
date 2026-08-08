import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useApp } from "../state/AppContext";

/** First run: POST /api/auth/setup creates the admin account. */
export function SetupPage() {
  const { setup } = useApp();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("تکرار گذرواژه یکسان نیست");
      return;
    }
    if (password.length < 6) {
      setError("گذرواژه باید دست‌کم ۶ نویسه باشد");
      return;
    }
    setBusy(true);
    try {
      await setup(username.trim(), password, displayName.trim());
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "خطا در راه‌اندازی");
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="brand-logo">Nu</div>
          <div>
            <h1 style={{ margin: 0 }}>راه‌اندازی NeurAI</h1>
            <div className="muted small">ساخت حساب مدیر — فقط بار اول</div>
          </div>
        </div>
        <p className="muted small">
          این سرور هنوز کاربری ندارد. اولین حساب، حساب <strong>مدیر</strong> است؛ بعداً
          کاربران دیگر را از بخش مدیریت اضافه کنید.
        </p>
        <label className="small muted">نام کاربری</label>
        <input
          className="input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          style={{ marginBottom: 10 }}
        />
        <label className="small muted">نام نمایشی</label>
        <input
          className="input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="مثلاً: سارا محمدی"
          style={{ marginBottom: 10 }}
        />
        <label className="small muted">گذرواژه (حداقل ۶ نویسه)</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ marginBottom: 10 }}
        />
        <label className="small muted">تکرار گذرواژه</label>
        <input
          className="input"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          style={{ marginBottom: 14 }}
        />
        {error && (
          <p className="badge danger" style={{ marginBottom: 12 }}>
            {error}
          </p>
        )}
        <button
          className="btn primary"
          style={{ width: "100%" }}
          disabled={busy || !username.trim() || !password}
        >
          {busy ? "در حال ساخت حساب…" : "ساخت حساب مدیر و ورود"}
        </button>
      </form>
    </div>
  );
}
