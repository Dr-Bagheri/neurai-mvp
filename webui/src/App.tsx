import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ActionItemsPage } from "./pages/ActionItemsPage";
import { AdminPage } from "./pages/AdminPage";
import { ChatPage } from "./pages/ChatPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LiveMeetingPage } from "./pages/LiveMeetingPage";
import { LoginPage } from "./pages/LoginPage";
import { MeetingPage } from "./pages/MeetingPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useApp } from "./state/AppContext";

export default function App() {
  const { user } = useApp();

  if (!user) return <LoginPage />;

  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/live" element={<LiveMeetingPage />} />
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
  );
}
