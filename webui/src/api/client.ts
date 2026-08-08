// The single place the UI gets data from. Today it serves the in-browser
// mock; when the FastAPI engine exists, each function body becomes a fetch
// to /api/* (types stay identical — they mirror the Pydantic schema).

import {
  CANNED_ANSWERS,
  FALLBACK_ANSWER,
  MOCK_ACTION_ITEMS,
  MOCK_AUDIT,
  MOCK_CHAT_SEED,
  MOCK_DISK,
  MOCK_DOCUMENTS,
  MOCK_ERRORS,
  MOCK_MEETINGS,
  MOCK_MODELS,
  MOCK_QUEUE,
  MOCK_RETENTION,
  MOCK_SEARCH,
  MOCK_STATUS,
  MOCK_USER,
} from "./mock";
import type {
  ActionItem,
  ActionItemStatus,
  AuditEntry,
  ChatMessage,
  DiskHealth,
  DocumentInfo,
  ErrorLogEntry,
  Meeting,
  ModelStatus,
  QueueJob,
  RetentionSettings,
  SearchHit,
  ServerStatus,
  User,
} from "./types";

const LATENCY_MS = 250;
const delay = <T,>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));

// Mutable copies so UI actions (relabel, status changes) persist in-session.
const meetings: Meeting[] = structuredClone(MOCK_MEETINGS);
const actionItems: ActionItem[] = structuredClone(MOCK_ACTION_ITEMS);
let status: ServerStatus = structuredClone(MOCK_STATUS);
let retention: RetentionSettings = structuredClone(MOCK_RETENTION);
let msgCounter = 100;

export const api = {
  async login(username: string, _password: string): Promise<User> {
    return delay({ ...MOCK_USER, username });
  },

  async getStatus(): Promise<ServerStatus> {
    return delay(structuredClone(status));
  },

  async setProfile(profile: ServerStatus["profile"]): Promise<ServerStatus> {
    status = { ...status, profile };
    return delay(structuredClone(status));
  },

  async setWorkspaceCloud(enabled: boolean): Promise<ServerStatus> {
    status = { ...status, cloud_enabled_workspace: enabled };
    return delay(structuredClone(status));
  },

  async listMeetings(): Promise<Meeting[]> {
    return delay(structuredClone(meetings));
  },

  async getMeeting(id: string): Promise<Meeting | null> {
    const m = meetings.find((x) => x.id === id) ?? null;
    return delay(m ? structuredClone(m) : null);
  },

  /** Manual relabel (D2): rename a speaker across all their segments. */
  async relabelSpeaker(meetingId: string, from: string, to: string): Promise<Meeting | null> {
    const m = meetings.find((x) => x.id === meetingId);
    if (!m) return delay(null);
    for (const s of m.segments) {
      if (s.speaker === from) s.speaker = to;
    }
    if (!m.participants.includes(to)) m.participants.push(to);
    return delay(structuredClone(m));
  },

  async saveNotes(meetingId: string, notes: string): Promise<void> {
    const m = meetings.find((x) => x.id === meetingId);
    if (m) m.notes = notes;
    return delay(undefined);
  },

  async listActionItems(): Promise<ActionItem[]> {
    return delay(structuredClone(actionItems));
  },

  async setActionItemStatus(id: string, newStatus: ActionItemStatus): Promise<ActionItem[]> {
    const a = actionItems.find((x) => x.id === id);
    if (a) a.status = newStatus;
    return delay(structuredClone(actionItems));
  },

  async listDocuments(): Promise<DocumentInfo[]> {
    return delay(structuredClone(MOCK_DOCUMENTS));
  },

  async searchTranscripts(query: string): Promise<SearchHit[]> {
    return delay(MOCK_SEARCH(query));
  },

  async listQueue(): Promise<QueueJob[]> {
    return delay(structuredClone(MOCK_QUEUE));
  },

  async listAudit(): Promise<AuditEntry[]> {
    return delay(structuredClone(MOCK_AUDIT));
  },

  // ---- D9 admin health page ----

  async getDiskHealth(): Promise<DiskHealth> {
    return delay(structuredClone(MOCK_DISK));
  },

  async listModels(): Promise<ModelStatus[]> {
    return delay(structuredClone(MOCK_MODELS));
  },

  async listErrors(): Promise<ErrorLogEntry[]> {
    return delay(structuredClone(MOCK_ERRORS));
  },

  async getRetention(): Promise<RetentionSettings> {
    return delay(structuredClone(retention));
  },

  async setRetention(next: RetentionSettings): Promise<RetentionSettings> {
    retention = { ...next };
    return delay(structuredClone(retention));
  },

  chatSeed(): ChatMessage[] {
    return structuredClone(MOCK_CHAT_SEED);
  },

  /** Mock of the harness tool-use loop: intent-matched canned skills. */
  async sendChat(text: string): Promise<ChatMessage> {
    const canned = CANNED_ANSWERS.find((c) => c.match.test(text));
    const body = canned ? canned.build() : FALLBACK_ANSWER();
    const reply: ChatMessage = { id: `c${++msgCounter}`, role: "assistant", ...body };
    // Simulate model latency a bit above data-call latency.
    return new Promise((resolve) => setTimeout(() => resolve(reply), 900));
  },
};
