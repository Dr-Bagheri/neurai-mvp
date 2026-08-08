import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ActionItemsPage } from "./pages/ActionItemsPage";
import { AdminPage } from "./pages/AdminPage";
import { ChatPage } from "./pages/ChatPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { LogsPage } from "./pages/LogsPage";
import { MeetingPage } from "./pages/MeetingPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SetupPage } from "./pages/SetupPage";
import { useApp } from "./state/AppContext";
import { ChatProvider } from "./state/ChatContext";

export default function App() {
  const { boot, retryBoot } = useApp();

  if (boot === "loading") {
    return (
      <div className="login-page">
        <p className="muted">در حال اتصال به سرور…</p>
      </div>
    );
  }
  if (boot === "offline") {
    return (
      <div className="login-page">
        <div className="card login-card" style={{ textAlign: "center" }}>
          <h2>سرور در دسترس نیست</h2>
          <p className="muted small">
            موتور NeurAI پاسخ نمی‌دهد. مطمئن شوید سرویس روی سرور دفتر اجراست، سپس دوباره
            تلاش کنید.
          </p>
          <button className="btn primary" onClick={retryBoot}>
            تلاش دوباره
          </button>
        </div>
      </div>
    );
  }
  if (boot === "needs_setup") return <SetupPage />;
  if (boot === "login") return <LoginPage />;

  return (
    <ChatProvider>
      <HashRouter>
        <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          {/* v0.3: live meeting merged into the meetings page */}
          <Route path="/live" element={<Navigate to="/" replace />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/meetings/:id" element={<MeetingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/actions" element={<ActionItemsPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </ChatProvider>
  );
}
