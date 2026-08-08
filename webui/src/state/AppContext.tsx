import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { ServerStatus, User } from "../api/types";
import { digits } from "../lib/digits";

interface Settings {
  persianDigits: boolean;
  theme: "light" | "dark";
}

interface AppState {
  user: User | null;
  status: ServerStatus | null;
  settings: Settings;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshStatus: () => Promise<void>;
  setSettings: (patch: Partial<Settings>) => void;
  /** Digit formatter honoring the Persian-digits setting. */
  d: (input: string | number) => string;
}

const Ctx = createContext<AppState | null>(null);

const SETTINGS_KEY = "neurai.settings";

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { persianDigits: true, theme: "light", ...JSON.parse(raw) };
  } catch {
    // fall through to defaults
  }
  return { persianDigits: true, theme: "light" };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [settings, setSettingsState] = useState<Settings>(loadSettings);

  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme;
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  }, [settings]);

  const refreshStatus = useCallback(async () => {
    setStatus(await api.getStatus());
  }, []);

  useEffect(() => {
    if (user) void refreshStatus();
  }, [user, refreshStatus]);

  const value = useMemo<AppState>(
    () => ({
      user,
      status,
      settings,
      login: async (username, password) => {
        setUser(await api.login(username, password));
      },
      logout: () => setUser(null),
      refreshStatus,
      setSettings: (patch) => setSettingsState((s) => ({ ...s, ...patch })),
      d: (input) => digits(input, settings.persianDigits),
    }),
    [user, status, settings, refreshStatus],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
