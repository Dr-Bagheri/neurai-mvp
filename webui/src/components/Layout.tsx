import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../state/AppContext";
import { AssistantPanel } from "./AssistantPanel";

// v0.3 menu: one Meetings entry (live controls + records merged), search in
// the top bar, assistant only as the left panel, Logs consolidating the
// queue + audit views.
const NAV = [
  { to: "/", icon: "🗓️", label: "جلسه‌ها" },
  { to: "/actions", icon: "✅", label: "کارها" },
  { to: "/documents", icon: "📄", label: "اسناد" },
  { to: "/settings", icon: "⚙️", label: "تنظیمات" },
];

const TITLES: Record<string, string> = {
  "/": "جلسه‌ها",
  "/chat": "بایگانی گفتگو با دستیار",
  "/search": "نتایج جستجو",
  "/actions": "پیگیری کارها",
  "/documents": "اسناد و پرسش‌وپاسخ",
  "/logs": "گزارش‌ها",
  "/settings": "تنظیمات",
  "/admin": "مدیریت سرور",
};

export function Layout() {
  const { user, adminStatus, logout, settings, setSettings } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const title =
    TITLES[location.pathname] ??
    (location.pathname.startsWith("/meetings/") ? "جزئیات جلسه" : "NeurAI");

  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    navigate(`/search?q=${encodeURIComponent(query.trim())}`);
    setQuery("");
  };

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
          <>
            <NavLink
              to="/logs"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              <span className="icon">📜</span>
              گزارش‌ها
            </NavLink>
            <NavLink
              to="/admin"
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              <span className="icon">🛠️</span>
              مدیریت سرور
            </NavLink>
          </>
        )}
        <div className="spacer" />
        <div className="nav-link" style={{ cursor: "default" }}>
          <span className="icon">👤</span>
          <span className="small">{user?.display_name}</span>
        </div>
        <button className="btn sm" onClick={() => void logout()}>
          خروج
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="title">{title}</div>
          <form className="topbar-search" onSubmit={submitSearch}>
            <input
              className="input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="🔎 جستجو در جلسه‌ها و اسناد…"
            />
          </form>
          <div className="controls">
            {adminStatus &&
              (adminStatus.profile === "air_gapped" ? (
                <span className="badge warn" title="حالت ایزوله: هیچ مسیر ابری فعال نیست">
                  ⛔ ایزوله
                </span>
              ) : adminStatus.cloud_allowed ? (
                <span className="badge cloud">☁️ ابر فعال</span>
              ) : (
                <span className="badge local">🏠 فقط مدل محلی</span>
              ))}
            {adminStatus?.live_meeting_active && (
              <span className="badge danger">● در حال ضبط</span>
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

      {/* Persistent assistant — docked at the physical LEFT edge; hidden only
          on the /chat archive page (the page itself is the full surface). */}
      {location.pathname !== "/chat" && <AssistantPanel />}
    </div>
  );
}
