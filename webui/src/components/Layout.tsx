import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../state/AppContext";

const NAV = [
  { to: "/", icon: "🗓️", label: "جلسه‌ها" },
  { to: "/live", icon: "🎙️", label: "جلسهٔ زنده" },
  { to: "/chat", icon: "💬", label: "دستیار" },
  { to: "/search", icon: "🔎", label: "جستجو" },
  { to: "/actions", icon: "✅", label: "کارها" },
  { to: "/documents", icon: "📄", label: "اسناد" },
  { to: "/settings", icon: "⚙️", label: "تنظیمات" },
];

const TITLES: Record<string, string> = {
  "/": "جلسه‌ها",
  "/live": "جلسهٔ زنده",
  "/chat": "دستیار هوشمند",
  "/search": "جستجو در همهٔ جلسه‌ها",
  "/actions": "پیگیری کارها",
  "/documents": "اسناد و پرسش‌وپاسخ",
  "/settings": "تنظیمات",
  "/admin": "مدیریت سرور",
};

export function Layout() {
  const { user, status, logout, settings, setSettings } = useApp();
  const location = useLocation();
  const title =
    TITLES[location.pathname] ??
    (location.pathname.startsWith("/meetings/") ? "جزئیات جلسه" : "NeurAI");

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">Nu</div>
          <span>NeurAI</span>
        </div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
          >
            <span className="icon">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
        {user?.is_admin && (
          <NavLink
            to="/admin"
            className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
          >
            <span className="icon">🛠️</span>
            مدیریت سرور
          </NavLink>
        )}
        <div className="spacer" />
        <div className="nav-link" style={{ cursor: "default" }}>
          <span className="icon">👤</span>
          <span className="small">{user?.display_name}</span>
        </div>
        <button className="btn sm" onClick={logout}>
          خروج
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="title">{title}</div>
          <div className="controls">
            {status &&
              (status.profile === "air_gapped" ? (
                <span className="badge warn" title="حالت ایزوله: هیچ مسیر ابری فعال نیست">
                  ⛔ ایزوله (Air-gapped)
                </span>
              ) : status.online ? (
                <span className="badge ok">🌐 آنلاین</span>
              ) : (
                <span className="badge plain">🔌 آفلاین — همه‌چیز محلی</span>
              ))}
            {status && !status.cloud_enabled_workspace && status.profile !== "air_gapped" && (
              <span className="badge local" title="مدل ابری برای این فضای کاری فعال نشده">
                🏠 فقط مدل محلی
              </span>
            )}
            <button
              className="btn sm"
              title="تغییر پوسته"
              onClick={() =>
                setSettings({ theme: settings.theme === "light" ? "dark" : "light" })
              }
            >
              {settings.theme === "light" ? "🌙" : "☀️"}
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
