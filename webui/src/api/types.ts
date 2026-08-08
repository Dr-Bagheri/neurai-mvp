// App-facing API types (D6). Named request/response models come from
// src/api/schema.d.ts, GENERATED from openapi.json — regenerate with
// `npm run gen:api` whenever the server schema changes; do not edit that file.
//
// Endpoints the server returns as plain dicts (list[dict(r)]) are typed here
// by hand against the route implementations in server/neurai/api/*.py.

import type { components } from "./schema";

type Schemas = components["schemas"];

// ---- generated models -------------------------------------------------------

export type User = Schemas["UserOut"];
export type Meeting = Schemas["MeetingOut"];
export type MeetingCreate = Schemas["MeetingCreate"];
export type TranscriptSegment = Schemas["SegmentOut"];
export type Credentials = Schemas["Credentials"];
export type SettingsUpdate = Schemas["SettingsUpdate"];

export type CaptureMode = "room" | "participants";
export type MeetingStatus = "created" | "live" | "processing" | "done" | "failed";
export type Sensitivity = "normal" | "confidential";
export type ConnectivityProfile = "air_gapped" | "auto";
export type Source = "local" | "cloud";

// ---- hand-typed dict responses (see server/neurai/api/*.py) -------------------

/** GET /api/auth/status */
export interface AuthStatus {
  needs_setup: boolean;
}

/** GET /api/meetings/{id}/bookmarks — meetings.py list_bookmarks */
export interface Bookmark {
  id: number;
  t_ms: number;
  note: string;
  created_at: string;
}

/** GET /api/meetings/{id}/notes — meetings.py list_notes */
export interface MeetingNote {
  id: number;
  t_ms: number | null;
  text: string;
  created_at: string;
}

/** GET /api/meetings/{id}/summaries — meetings.py list_summaries */
export interface Summary {
  id: number;
  kind: string; // "summary" | "action_items" | "minutes" | ...
  content: string;
  source: Source;
  model: string;
  created_at: string;
}

/** GET /api/series — meetings.py list_series */
export interface Series {
  id: number;
  title: string;
  created_at: string;
}

/** GET /api/action-items — action_items.py (SELECT * FROM action_items) */
export interface ActionItem {
  id: number;
  meeting_id: number | null;
  owner_id: number;
  assignee: string;
  text: string;
  due_date: string | null;
  status: "open" | "done" | "dropped";
  created_at: string;
  updated_at: string;
}

/** GET /api/documents — documents.py list_documents */
export interface DocumentInfo {
  id: number;
  filename: string;
  mime: string;
  status: string; // "uploaded" | "indexed" | ...
  created_at: string;
}

/** POST /api/search — search.py */
export interface SearchHit {
  kind: "transcript" | "document";
  ref_id: number; // meeting_id or document_id
  seq: number;
  text: string;
  score: number;
}

/** GET /api/chats — chat.py list_chats */
export interface ChatInfo {
  id: number;
  title: string;
  created_at: string;
}

/** GET /api/chats/{id}/messages — chat.py list_messages */
export interface StoredChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  source: string;
  provenance: string; // JSON array string of resource labels
  created_at: string;
}

/** POST /api/chats/{id}/messages and /confirm — chat.py send_message */
export type SendMessageResult =
  | {
      type: "message";
      id: number;
      content: string;
      source: Source;
      provenance: string[];
      via?: string;
      fell_back?: boolean;
      result?: Record<string, unknown>;
    }
  | {
      type: "confirmation_required";
      skill: string;
      params: Record<string, unknown>;
      message: string;
    };

/** GET /api/admin/settings — admin.py get_settings */
export interface AdminSettings {
  connectivity_profile: ConnectivityProfile;
  cloud_enabled: boolean;
  local_chat_model: string;
  cloud_chat_model: string;
  embed_model: string;
  openrouter_key_set: boolean;
}

/** GET /api/admin/status — admin.py system_status */
export interface AdminStatus {
  profile: ConnectivityProfile;
  cloud_allowed: boolean;
  live_meeting_active: boolean;
  jobs: Record<string, number>; // status → count
  users: number;
  meetings: number;
}

/** GET /api/admin/jobs — admin.py list_jobs */
export interface JobRow {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  priority: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** GET /api/admin/audit — admin.py audit_log */
export interface AuditRow {
  id: number;
  user_id: number;
  username: string | null;
  skill: string;
  params: string;
  resource: string;
  source: Source;
  ok: number;
  error: string | null;
  created_at: string;
}

/** GET /api/admin/users — admin.py list_users */
export interface AdminUserRow {
  id: number;
  username: string;
  display_name: string;
  is_admin: number;
  created_at: string;
}

/** /ws/meetings/{id}/captions events — audio/session.py _broadcast */
export type CaptionEvent =
  | { type: "caption"; segment_id: number; start_ms: number; end_ms: number; text: string }
  | { type: "ended" };
