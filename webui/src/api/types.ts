// Shape mirror of the future FastAPI/Pydantic schema (D6: these will be
// generated via openapi-typescript once the server exists; keep field names
// snake_case to match).

export type Provenance = "local" | "cloud";
export type ConnectivityProfile = "air_gapped" | "auto";
export type CaptureMode = "per_participant" | "room_mic";
export type MeetingStatus = "live" | "processing" | "ready";
export type ActionItemStatus = "open" | "in_progress" | "done";
export type JobStatus = "running" | "queued" | "done";
export type Sensitivity = "normal" | "confidential"; // «محرمانه» (D4 data lifecycle)

export interface User {
  id: string;
  username: string;
  display_name: string;
  is_admin: boolean;
  has_voice_profile: boolean;
}

export interface TranscriptSegment {
  id: string;
  start_s: number;
  end_s: number;
  speaker: string | null; // null = not yet diarized (live pass)
  text: string;
  bookmarked?: boolean;
}

export interface Bookmark {
  id: string;
  at_s: number;
  label: string;
}

export interface ActionItem {
  id: string;
  meeting_id: string;
  meeting_title: string;
  text: string;
  assignee: string;
  due_date: string | null; // ISO
  status: ActionItemStatus;
}

export interface MeetingSummary {
  overview: string;
  decisions: string[];
  provenance: Provenance;
}

export interface Meeting {
  id: string;
  title: string;
  started_at: string; // ISO
  duration_s: number;
  status: MeetingStatus;
  capture_mode: CaptureMode;
  local_only: boolean;
  sensitivity: Sensitivity;
  is_series: boolean;
  series_name: string | null;
  participants: string[];
  segments: TranscriptSegment[];
  bookmarks: Bookmark[];
  notes: string;
  summary: MeetingSummary | null;
}

export interface DocumentInfo {
  id: string;
  name: string;
  pages: number;
  indexed_at: string; // ISO
}

export interface Citation {
  kind: "meeting" | "document";
  ref_id: string;
  title: string;
  snippet: string;
}

export interface SkillCall {
  skill: string;
  args: Record<string, string>;
  side_effect: boolean; // true → needs explicit user confirmation (D7 rule 2)
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  provenance?: Provenance;
  skill_calls?: SkillCall[];
  citations?: Citation[];
  pending_confirmation?: SkillCall | null;
}

export interface SearchHit {
  meeting_id: string;
  meeting_title: string;
  started_at: string;
  segment: TranscriptSegment;
}

export interface QueueJob {
  id: string;
  kind: string;
  label: string;
  status: JobStatus;
  progress: number; // 0..1
}

export interface AuditEntry {
  id: string;
  at: string; // ISO
  username: string;
  skill: string;
  resource: string;
  provenance: Provenance;
}

export interface ServerStatus {
  online: boolean;
  profile: ConnectivityProfile;
  cloud_enabled_workspace: boolean;
  live_meeting_id: string | null;
  ram_used_gb: number;
  ram_total_gb: number;
}

// ---- D9 admin health page ----

export interface DiskHealth {
  used_gb: number;
  total_gb: number;
  audio_gb: number;
  /** Projected days until the disk fills at the current growth rate. */
  projected_full_days: number;
}

export interface ModelStatus {
  name: string;
  role: string;
  version: string;
  loaded: boolean;
}

export interface ErrorLogEntry {
  id: string;
  at: string; // ISO
  source: string;
  message: string;
}

export interface RetentionSettings {
  audio_days: number; // 0 = keep forever
  transcript_days: number; // 0 = keep until deleted
}
