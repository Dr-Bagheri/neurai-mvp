// Real API client for the FastAPI engine (D1/D6). Session-cookie auth,
// same-origin in production (the server serves this bundle); the Vite dev
// server proxies /api and /ws to 127.0.0.1:8471.

import type {
  ActionItem,
  AdminMeetingRow,
  AdminSettings,
  AdminStatus,
  AdminUserRow,
  AuditFileRecord,
  AuditRow,
  AuditVerifyResult,
  AuthStatus,
  Bookmark,
  ChatInfo,
  CloudReadiness,
  CloudStatus,
  DocumentInfo,
  JobRow,
  Meeting,
  MeetingCreate,
  MeetingMic,
  MeetingNote,
  MeetingProgress,
  ModeStatus,
  ServerMode,
  SearchHit,
  SendMessageResult,
  Series,
  SettingsUpdate,
  StoredChatMessage,
  Summary,
  TranscriptSegment,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    /** FastAPI `detail` — the server sends user-facing Persian messages. */
    public detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers:
      init?.body !== undefined && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : undefined,
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  // ---- auth (auth.py) ----
  authStatus: () => get<AuthStatus>("/api/auth/status"),
  setup: (username: string, password: string, display_name = "") =>
    post<User>("/api/auth/setup", { username, password, display_name }),
  login: (username: string, password: string) =>
    post<User>("/api/auth/login", { username, password }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),
  me: () => get<User>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    post<{ ok: boolean }>("/api/auth/change-password", { current_password, new_password }),
  createUser: (username: string, password: string, display_name = "") =>
    post<User>("/api/auth/users", { username, password, display_name }),

  // ---- meetings (meetings.py) ----
  listMeetings: () => get<Meeting[]>("/api/meetings"),
  createMeeting: (body: MeetingCreate) => post<Meeting>("/api/meetings", body),
  getMeeting: (id: number) => get<Meeting>(`/api/meetings/${id}`),
  deleteMeeting: (id: number) =>
    request<{ ok: boolean }>(`/api/meetings/${id}`, { method: "DELETE" }),
  startMeeting: (id: number) => post<{ ok: boolean; status: string }>(`/api/meetings/${id}/start`),
  stopMeeting: (id: number) => post<{ ok: boolean; status: string }>(`/api/meetings/${id}/stop`),
  getTranscript: (id: number) => get<TranscriptSegment[]>(`/api/meetings/${id}/transcript`),
  relabelSpeaker: (id: number, label: string, display_name: string) =>
    post<{ ok: boolean }>(`/api/meetings/${id}/speakers/relabel`, { label, display_name }),
  /** For the <audio> element — Range-seekable WAV synthesized by the server.
   * mic_id selects a specific mic's recording (omit → first mic). */
  audioUrl: (id: number, micId?: number) =>
    micId !== undefined
      ? `/api/meetings/${id}/audio?mic_id=${micId}`
      : `/api/meetings/${id}/audio`,
  // Named multi-mic registry (D2 v0.3).
  listMics: (id: number) => get<MeetingMic[]>(`/api/meetings/${id}/mics`),
  addMic: (id: number, name: string) =>
    post<MeetingMic>(`/api/meetings/${id}/mics`, { name }),
  /** Rename works before AND during the meeting. */
  renameMic: (id: number, micId: number, name: string) =>
    request<{ ok: boolean }>(`/api/meetings/${id}/mics/${micId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  /** 409 once the mic has recorded audio. */
  deleteMic: (id: number, micId: number) =>
    request<{ ok: boolean }>(`/api/meetings/${id}/mics/${micId}`, { method: "DELETE" }),
  /** D15 per-meeting cloud-ASR consent; only before start; 409 offline/«محرمانه». */
  setCloudTranscribe: (id: number, enabled: boolean) =>
    request<{ ok: boolean }>(`/api/meetings/${id}/cloud-transcribe`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  /** Quality-pass percent while status=="processing" (done → 100). */
  meetingProgress: (id: number) =>
    get<MeetingProgress>(`/api/meetings/${id}/progress`),
  addBookmark: (id: number, t_ms: number, note = "") =>
    post<{ id: number }>(`/api/meetings/${id}/bookmarks`, { t_ms, note }),
  listBookmarks: (id: number) => get<Bookmark[]>(`/api/meetings/${id}/bookmarks`),
  addNote: (id: number, text: string, t_ms: number | null = null) =>
    post<{ id: number }>(`/api/meetings/${id}/notes`, { text, t_ms }),
  listNotes: (id: number) => get<MeetingNote[]>(`/api/meetings/${id}/notes`),
  listSummaries: (id: number) => get<Summary[]>(`/api/meetings/${id}/summaries`),
  exportUrl: (id: number, filename: string) =>
    `/api/meetings/${id}/exports/${encodeURIComponent(filename)}`,

  // ---- series ----
  listSeries: () => get<Series[]>("/api/series"),
  createSeries: (title: string) => post<{ id: number; title: string }>("/api/series", { title }),

  // ---- chat (chat.py) ----
  listChats: () => get<ChatInfo[]>("/api/chats"),
  createChat: (title = "") => post<{ id: number; title: string }>("/api/chats", { title }),
  listChatMessages: (chatId: number) =>
    get<StoredChatMessage[]>(`/api/chats/${chatId}/messages`),
  sendChatMessage: (
    chatId: number,
    content: string,
    allow_cloud = false,
    signal?: AbortSignal,
  ) =>
    request<SendMessageResult>(`/api/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, allow_cloud }),
      signal,
    }),
  /** Stop button: aborts the in-flight LLM generation server-side. */
  cancelGeneration: (chatId: number) =>
    post<{ cancelled: boolean }>(`/api/chats/${chatId}/cancel`),
  confirmSkill: (
    chatId: number,
    skill: string,
    params: Record<string, unknown>,
    allow_cloud = false,
  ) => post<SendMessageResult>(`/api/chats/${chatId}/confirm`, { skill, params, allow_cloud }),

  // ---- action items (action_items.py) ----
  listActionItems: (status?: string) =>
    get<ActionItem[]>(`/api/action-items${status ? `?status=${status}` : ""}`),
  updateActionItem: (
    id: number,
    patch: Partial<Pick<ActionItem, "text" | "assignee" | "due_date" | "status">>,
  ) => request<{ ok: boolean }>(`/api/action-items/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  }),
  resurface: (seriesId: number) => get<ActionItem[]>(`/api/action-items/resurface/${seriesId}`),

  // ---- documents (documents.py) ----
  listDocuments: () => get<DocumentInfo[]>("/api/documents"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ id: number; filename: string; status: string }>("/api/documents", {
      method: "POST",
      body: form,
    });
  },
  deleteDocument: (id: number) =>
    request<{ ok: boolean }>(`/api/documents/${id}`, { method: "DELETE" }),

  // ---- search (search.py) ----
  search: (query: string, kind?: "transcript" | "document", top_k = 8) =>
    post<SearchHit[]>("/api/search", { query, kind: kind ?? null, top_k }),

  // ---- admin (admin.py) ----
  adminSettings: () => get<AdminSettings>("/api/admin/settings"),
  updateAdminSettings: (patch: SettingsUpdate) =>
    request<AdminSettings>("/api/admin/settings", { method: "PUT", body: JSON.stringify(patch) }),
  adminStatus: () => get<AdminStatus>("/api/admin/status"),
  adminJobs: () => get<JobRow[]>("/api/admin/jobs"),
  adminAudit: () => get<AuditRow[]>("/api/admin/audit"),
  adminUsers: () => get<AdminUserRow[]>("/api/admin/users"),
  /** Booleans only — drives enabled/disabled state of the cloud buttons. */
  cloudStatus: () => get<CloudStatus>("/api/admin/cloud-status"),
  /** D15: the one Offline/Online switch. PUT is probe-gated (409 Persian). */
  getMode: () => get<ModeStatus>("/api/admin/mode"),
  setMode: (mode: ServerMode) =>
    request<ModeStatus>("/api/admin/mode", { method: "PUT", body: JSON.stringify({ mode }) }),
  /** Manual encrypted snapshot backup to Supabase (queued job). */
  backupNow: () => post<{ job_id: number }>("/api/admin/backup"),
  adminAllMeetings: () => get<AdminMeetingRow[]>("/api/admin/meetings"),
  adminRemoveMeeting: (id: number) =>
    request<{ ok: boolean }>(`/api/admin/meetings/${id}`, { method: "DELETE" }),
  adminAuditFile: () => get<AuditFileRecord[]>("/api/admin/audit-file"),
  adminAuditVerify: () => get<AuditVerifyResult>("/api/admin/audit-file/verify"),

  // ---- system (any authenticated user) ----
  /** Cloud readiness + reason enum — drives non-admin cloud toggles. */
  cloudReadiness: () => get<CloudReadiness>("/api/cloud"),

  // ---- health ----
  health: () => get<{ ok: boolean; version: string }>("/api/health"),
};

/** WebSocket URL helper (same host; ws/wss follows the page scheme). */
export function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${path}`;
}
