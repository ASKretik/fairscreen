import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { checkHealth } from "./api";
import { apiConfigured } from "./env";

/** checking → ok, or checking → slow (after 2 s) → ok | down. */
export type ServerStatus = "checking" | "slow" | "ok" | "down";

const SLOW_AFTER_MS = 2000;

interface ServerStatusState {
  status: ServerStatus;
  retry(): void;
}

const Ctx = createContext<ServerStatusState>({ status: "checking", retry: () => {} });

/** Calls /health on app load to wake the Render instance (SPEC §9 "Render cold start"). */
export function ServerStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ServerStatus>("checking");
  const attempt = useRef(0);

  const check = useCallback(() => {
    if (!apiConfigured) return; // demo-only deployment: there is no server to wake
    const id = ++attempt.current;
    setStatus("checking");
    const timer = setTimeout(() => {
      if (attempt.current === id) setStatus((s) => (s === "checking" ? "slow" : s));
    }, SLOW_AFTER_MS);
    checkHealth().then((ok) => {
      clearTimeout(timer);
      if (attempt.current === id) setStatus(ok ? "ok" : "down");
    });
  }, []);

  useEffect(check, [check]);

  return <Ctx.Provider value={{ status, retry: check }}>{children}</Ctx.Provider>;
}

export function useServerStatus(): ServerStatusState {
  return useContext(Ctx);
}
