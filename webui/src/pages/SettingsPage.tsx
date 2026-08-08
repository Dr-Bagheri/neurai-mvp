import { useApp } from "../state/AppContext";

export function SettingsPage() {
  const { user, settings, setSettings } = useApp();

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
        <h3>پروفایل صوتی (اختیاری)</h3>
        <p className="muted small">
          با ضبط حدود ۳۰ ثانیه از صدای خود، در جلسه‌های «میکروفون اتاق» به‌صورت خودکار
          شناسایی می‌شوید — بدون نیاز به دور معارفه. پروفایل فقط یک بردار صوتی است، روی سرور
          دفتر می‌ماند و هر زمان می‌توانید حذفش کنید.
        </p>
        {user?.has_voice_profile ? (
          <div className="row">
            <span className="badge ok">✓ پروفایل صوتی ثبت شده</span>
            <button
              className="btn danger sm"
              onClick={() => window.alert("در نسخهٔ نمایشی غیرفعال است.")}
            >
              حذف پروفایل
            </button>
          </div>
        ) : (
          <button
            className="btn primary"
            onClick={() => window.alert("در نسخهٔ نمایشی ضبط غیرفعال است.")}
          >
            🎙️ ضبط پروفایل صوتی
          </button>
        )}
      </div>

      <div className="card">
        <h3>حساب کاربری</h3>
        <p className="muted small" style={{ marginBottom: 0 }}>
          نام کاربری: <strong>{user?.username}</strong> · حساب‌ها محلی‌اند و روی سرور دفتر
          نگهداری می‌شوند؛ برای تغییر گذرواژه به مدیر سیستم مراجعه کنید.
        </p>
      </div>
    </>
  );
}
