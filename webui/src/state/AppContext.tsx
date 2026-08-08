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
import type {
  AdminStatus,
  CloudReadiness,
  CloudStatus,
  SendMessageResult,
  User,
} from "../api/types";
import { digits } from "../lib/digits";

interface Settings {
  persianDigits: boolean;
  theme: "light" | "dark";
  /** Persistent assistant panel (left dock) — open by default. */
  assistantOpen: boolean;
}

type Boot = "loading" | "needs_setup" | "login" | "ready" | "offline";

/** In-flight chat generation. Lives here (above the router) so navigating
 * away from the chat page never orphans the request — the reply is consumed
 * whenever the page remounts. */
export interface ChatGeneration {
  chatId: number;
  status: "generating" | "done" | "error";
  result?: SendMessageResult;
  error?: string;
}

interface AppState {
  boot: Boot;
  user: User | null;
  /** Admin-only server status; null for regular users. */
  adminStatus: AdminStatus | null;
  /** Admin-only cloud readiness (booleans); null for regular users. */
  cloudStatus: CloudStatus | null;
  /** Cloud readiness for EVERY authenticated user (GET /api/cloud). */
  cloudReadiness: CloudReadiness | null;
  refreshCloudReadiness: () => Promise<void>;
  settings: Settings;
  chatGen: ChatGeneration | null;
  startGeneration: (chatId: number, content: string, allowCloud: boolean) => void;
  /** Stop button: server-side cancel first; fetch-abort only as fallback. */
  stopGeneration: () => Promise<void>;
  clearGeneration: () => void;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAdminStatus: () => Promise<void>;
  retryBoot: () => void;
  setSettings: (patch: Partial<Settings>) => void;
  /** Digit formatter honoring the Persian-digits setting. */
  d: (input: string | number) => string;
}

const Ctx = createContext<AppState | null>(null);

const SETTINGS_KEY = "neurai.settings";

const DEFAULT_SETTINGS: Settings = {
  persianDigits: true,
  theme: "light",
  assistantOpen: true,
};

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    // fall through to defaults
  }
  return { ...DEFAULT_SETTINGS };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [boot, setBoot] = useState<Boot>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [cloudStatus, setCloudStatus] = useState<CloudStatus | null>(null);
  const [cloudReadiness, setCloudReadiness] = useState<CloudReadiness | null>(null);
  const [settings, setSettingsState] = useState<Settings>(loadSettings);
  const [bootNonce, setBootNonce] = useState(0);
  const [chatGen, setChatGen] = useState<ChatGeneration | null>(null);
  const genAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme;
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  // Boot: first-run check, then session-cookie restore.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBoot("loading");
      try {
        const status = await api.authStatus();
        if (cancelled) return;
        if (status.needs_setup) {
          setBoot("needs_setup");
          return;
        }
        try {
          const me = await api.me();
          if (cancelled) return;
          setUser(me);
          setBoot("ready");
        } catch (e) {
          if (cancelled) return;
          if (e instanceof ApiError && e.status === 401) setBoot("login");
          else setBoot("offline");
        }
      } catch {
        if (!cancelled) setBoot("offline"); // engine not reachable
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bootNonce]);

  const refreshAdminStatus = useCallback(async () => {
    try {
      setAdminStatus(await api.adminStatus());
    } catch {
      setAdminStatus(null);
    }
    try {
      setCloudStatus(await api.cloudStatus());
    } catch {
      setCloudStatus(null);
    }
  }, []);

  const startGeneration = useCallback(
    (chatId: number, content: string, allowCloud: boolean) => {
      const controller = new AbortController();
      genAbortRef.current = controller;
      setChatGen({ chatId, status: "generating" });
      void api
        .sendChatMessage(chatId, content, allowCloud, controller.signal)
        .then((result) => setChatGen({ chatId, status: "done", result }))
        .catch((e) => {
          if (controller.signal.aborted) {
            // fallback path only — normally the server cancel resolves the
            // request with {type:"stopped"} before we ever abort
            setChatGen({
              chatId,
              status: "done",
              result: { type: "stopped", id: -1, content: "⏹ تولید پاسخ متوقف شد." },
            });
          } else {
            setChatGen({
              chatId,
              status: "error",
              error: e instanceof ApiError ? e.detail : "ارسال پیام ممکن نشد",
            });
          }
        });
    },
    [],
  );

  const stopGeneration = useCallback(async () => {
    const gen = chatGen;
    if (!gen || gen.status !== "generating") return;
    try {
      const { cancelled } = await api.cancelGeneration(gen.chatId);
      // nothing registered server-side (already finished, or never started):
      // abort the fetch so the UI doesn't hang
      if (!cancelled) genAbortRef.current?.abort();
    } catch {
      genAbortRef.current?.abort();
    }
  }, [chatGen]);

  const clearGeneration = useCallback(() => {
    genAbortRef.current = null;
    setChatGen(null);
  }, []);

  const refreshCloudReadiness = useCallback(async () => {
    try {
      setCloudReadiness(await api.cloudReadiness());
    } catch {
      setCloudReadiness(null);
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) void refreshAdminStatus();
    else setAdminStatus(null);
    if (user) void refreshCloudReadiness();
    else setCloudReadiness(null);
  }, [user, refreshAdminStatus, refreshCloudReadiness]);

  const value = useMemo<AppState>(
    () => ({
      boot,
      user,
      adminStatus,
      cloudStatus,
      cloudReadiness,
      refreshCloudReadiness,
      settings,
      chatGen,
      startGeneration,
      stopGeneration,
      clearGeneration,
      login: async (username, password) => {
        setUser(await api.login(username, password));
        setBoot("ready");
      },
      setup: async (username, password, displayName) => {
        setUser(await api.setup(username, password, displayName));
        setBoot("ready");
      },
      logout: async () => {
        try {
          await api.logout();
        } finally {
          setUser(null);
          setBoot("login");
        }
      },
      refreshAdminStatus,
      retryBoot: () => setBootNonce((n) => n + 1),
      setSettings: (patch) => setSettingsState((s) => ({ ...s, ...patch })),
      d: (input) => digits(input, settings.persianDigits),
    }),
    [
      boot,
      user,
      adminStatus,
      cloudStatus,
      cloudReadiness,
      refreshCloudReadiness,
      settings,
      chatGen,
      startGeneration,
      stopGeneration,
      clearGeneration,
      refreshAdminStatus,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
