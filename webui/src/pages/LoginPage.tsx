import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useApp } from "../state/AppContext";

export function LoginPage() {
  const { login } = useApp();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "اتصال به سرور برقرار نشد");
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="brand-logo">Nu</div>
          <div>
            <h1 style={{ margin: 0 }}>NeurAI</h1>
            <div className="muted small">دستیار هوشمند جلسات — روی سرور دفتر شما</div>
          </div>
        </div>
        <label className="small muted">نام کاربری</label>
        <input
          className="input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          style={{ marginBottom: 10 }}
        />
        <label className="small muted">گذرواژه</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ marginBottom: 16 }}
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
          {busy ? "در حال ورود…" : "ورود"}
        </button>
        <p className="muted small" style={{ marginTop: 14, marginBottom: 0 }}>
          حساب‌ها محلی و روی سرور دفتر شما هستند؛ هیچ داده‌ای به اینترنت ارسال نمی‌شود.
        </p>
      </form>
    </div>
  );
}
