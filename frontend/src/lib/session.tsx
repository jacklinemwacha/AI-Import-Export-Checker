import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { loadSettings, saveSettings, DEMO_USERS, type Settings } from "./api";

type Ctx = { settings: Settings | null; ready: boolean; setSettings: (s: Settings | null) => void };
const SessionCtx = createContext<Ctx>({ settings: null, ready: false, setSettings: () => {} });

export function SessionProvider({ children }: { children: ReactNode }) {
  const [settings, set] = useState<Settings | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    set(loadSettings());
    setReady(true);
  }, []);
  const setSettings = (s: Settings | null) => {
    saveSettings(s);
    set(s);
  };
  return <SessionCtx.Provider value={{ settings, ready, setSettings }}>{children}</SessionCtx.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionCtx);
  const user = ctx.settings ? DEMO_USERS.find((u) => u.email === ctx.settings!.email) : undefined;
  return { ...ctx, user };
}

export const ROLE_LABEL: Record<string, string> = {
  importer: "Importer",
  clearing_agent: "Clearing agent",
  reviewer: "Reviewer",
  admin: "Admin",
};
