// Shared assistant conversation state. Both surfaces — the persistent left
// panel (all routes) and the /chat archive page — render from here, so there
// is exactly ONE consumer of the AppContext generation state machine and no
// double-append when a reply lands while either surface is (un)mounted.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError } from "../api/client";
import type { SendMessageResult } from "../api/types";
import { useApp } from "./AppContext";

/** Exact text the server stores for a user-stopped reply (chat.py STOPPED_FA). */
export const STOPPED_FA = "⏹ تولید پاسخ متوقف شد.";

export interface PendingConfirmation {
  skill: string;
  params: Record<string, unknown>;
}

export interface UiMessage {
  key: string;
  role: "user" | "assistant";
  text: string;
  source?: string;
  provenance?: string[];
  via?: string;
  fellBack?: boolean;
  stopped?: boolean;
  pendingConfirmation?: PendingConfirmation | null;
}

const CLOUD_REASON_FA: Record<string, string> = {
  air_gapped: "حالت ایزوله فعال است",
  offline_mode: "سرور در حالت آفلاین است", // D15
  cloud_disabled: "مدیر قابلیت ابری را غیرفعال کرده است", // pre-D15 servers
  no_api_key: "کلید API تنظیم نشده است",
};

interface ChatState {
  messages: UiMessage[];
  loaded: boolean;
  error: string;
  generating: boolean;
  stopping: boolean;
  allowCloud: boolean;
  setAllowCloud: (v: boolean) => void;
  cloudDisabledReason: string | null;
  send: (text: string) => Promise<void>;
  stop: () => Promise<void>;
  resolveConfirmation: (
    key: string,
    confirmation: PendingConfirmation,
    approved: boolean,
  ) => Promise<void>;
  /** Bumped after every CONFIRMED side-effectful skill (D7 rule 2) — pages
   * watch this to refetch state the assistant may have changed. */
  mutationCounter: number;
}

const Ctx = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const {
    user,
    chatGen,
    startGeneration,
    stopGeneration,
    clearGeneration,
    cloudReadiness,
    refreshCloudReadiness,
    refreshAdminStatus,
  } = useApp();

  const [chatId, setChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [stopping, setStopping] = useState(false);
  const [allowCloud, setAllowCloud] = useState(false);
  const [mutationCounter, setMutationCounter] = useState(0);
  const keyCounter = useRef(0);

  const nextKey = () => `k${++keyCounter.current}`;

  const generating = chatGen?.status === "generating" && chatGen.chatId === chatId;

  // Load (or reset) the conversation when the signed-in user changes.
  useEffect(() => {
    setChatId(null);
    setMessages([]);
    setLoaded(false);
    setError("");
    if (!user) return;
    let cancelled = false;
    void (async () => {
      try {
        const chats = await api.listChats();
        if (cancelled || chats.length === 0) return;
        setChatId(chats[0].id);
        const stored = await api.listChatMessages(chats[0].id);
        if (cancelled) return;
        setMessages(
          stored.map((m) => ({
            key: `s${m.id}`,
            role: m.role,
            text: m.content,
            source: m.role === "assistant" ? m.source : undefined,
            provenance:
              m.role === "assistant"
                ? (() => {
                    try {
                      const arr = JSON.parse(m.provenance);
                      return Array.isArray(arr) ? arr.map(String) : [];
                    } catch {
                      return [];
                    }
                  })()
                : undefined,
            stopped: m.role === "assistant" && m.content === STOPPED_FA,
          })),
        );
      } catch {
        // no chats yet is fine
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const applyResult = useCallback((result: SendMessageResult) => {
    if (result.type === "confirmation_required") {
      setMessages((m) => [
        ...m,
        {
          key: nextKey(),
          role: "assistant",
          text: result.message || "این عمل نیاز به تأیید شما دارد.",
          pendingConfirmation: { skill: result.skill, params: result.params },
        },
      ]);
      return;
    }
    const key = result.id > 0 ? `s${result.id}` : nextKey();
    setMessages((m) => {
      if (m.some((msg) => msg.key === key)) return m; // already loaded from server
      if (result.type === "stopped") {
        return [...m, { key, role: "assistant", text: result.content, stopped: true }];
      }
      return [
        ...m,
        {
          key,
          role: "assistant",
          text: result.content,
          source: result.source,
          provenance: result.provenance,
          via: result.via,
          fellBack: result.fell_back,
        },
      ];
    });
  }, []);

  // Single consumer of the generation state machine.
  useEffect(() => {
    if (!loaded || !chatGen || chatGen.status === "generating") return;
    if (chatGen.chatId !== chatId) return;
    if (chatGen.status === "done" && chatGen.result) applyResult(chatGen.result);
    if (chatGen.status === "error") setError(chatGen.error ?? "خطا");
    setStopping(false);
    clearGeneration();
  }, [chatGen, chatId, loaded, applyResult, clearGeneration]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || chatGen?.status === "generating") return;
      setError("");
      try {
        let id = chatId;
        if (id === null) {
          id = (await api.createChat()).id;
          setChatId(id);
        }
        setMessages((m) => [...m, { key: nextKey(), role: "user", text: trimmed }]);
        startGeneration(id, trimmed, allowCloud);
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : "ارسال پیام ممکن نشد");
      }
    },
    [chatId, chatGen, allowCloud, startGeneration],
  );

  const stop = useCallback(async () => {
    setStopping(true);
    await stopGeneration();
  }, [stopGeneration]);

  const resolveConfirmation = useCallback(
    async (key: string, confirmation: PendingConfirmation, approved: boolean) => {
      setMessages((m) =>
        m.map((msg) => (msg.key === key ? { ...msg, pendingConfirmation: null } : msg)),
      );
      if (!approved) {
        setMessages((m) => [
          ...m,
          { key: nextKey(), role: "assistant", text: "باشه، انجام نشد.", source: "local" },
        ]);
        return;
      }
      if (chatId === null) return;
      try {
        applyResult(await api.confirmSkill(chatId, confirmation.skill, confirmation.params, allowCloud));
        // The skill had side effects — let every page refetch what it shows.
        setMutationCounter((n) => n + 1);
        void refreshAdminStatus();
        void refreshCloudReadiness();
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : "اجرای مهارت ممکن نشد");
      }
    },
    [chatId, allowCloud, applyResult, refreshAdminStatus, refreshCloudReadiness],
  );

  const cloudDisabledReason =
    cloudReadiness && !cloudReadiness.cloud_ready
      ? (CLOUD_REASON_FA[cloudReadiness.reason] ?? cloudReadiness.reason)
      : null;

  const value = useMemo<ChatState>(
    () => ({
      messages,
      loaded,
      error,
      generating,
      stopping,
      allowCloud,
      setAllowCloud,
      cloudDisabledReason,
      send,
      stop,
      resolveConfirmation,
      mutationCounter,
    }),
    [
      messages,
      loaded,
      error,
      generating,
      stopping,
      allowCloud,
      cloudDisabledReason,
      send,
      stop,
      resolveConfirmation,
      mutationCounter,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChat(): ChatState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useChat must be used inside ChatProvider");
  return ctx;
}
