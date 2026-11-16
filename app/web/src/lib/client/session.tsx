"use client";

import { createContext, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { useI18n } from "@/lib/i18n/provider";
import { useAccount, type AccountState } from "./account";
import { callMessages } from "./api";
import { SessionStore, type ClientBinding, type SessionSnapshot } from "./session-store";

type SessionActions = Pick<
  SessionStore,
  | "start"
  | "resume"
  | "restart"
  | "forget"
  | "answerBase"
  | "answerAllBase"
  | "submitPortfolio"
  | "confirmPortfolio"
  | "skipPortfolio"
  | "reply"
  | "updateSettings"
  | "refreshProfile"
  | "retry"
  | "dismissError"
  | "clearRuns"
  | "getState"
>;

export type SessionValue = SessionSnapshot & SessionActions;

const SessionContext = createContext<SessionValue | null>(null);

function bindingOf(account: Exclude<AccountState, { status: "loading" }>): ClientBinding {
  if (account.status === "signed_in") return { source: "account", clientId: account.user.client_id };
  return account.status === "signed_out" ? { source: "none" } : { source: "browser" };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const { locale, t } = useI18n();
  const [store] = useState(() => new SessionStore());
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);

  useEffect(() => {
    store.configure(locale, callMessages(t));
  }, [store, locale, t]);

  const account = useAccount();
  useEffect(() => {
    // The client_id waits for /api/auth/me: with sign-in on, only the account's is accepted.
    if (account.status !== "loading") void store.init(bindingOf(account));
  }, [store, account]);

  const value = useMemo<SessionValue>(
    () => ({
      ...snapshot,
      start: store.start,
      resume: store.resume,
      restart: store.restart,
      forget: store.forget,
      answerBase: store.answerBase,
      answerAllBase: store.answerAllBase,
      submitPortfolio: store.submitPortfolio,
      confirmPortfolio: store.confirmPortfolio,
      skipPortfolio: store.skipPortfolio,
      reply: store.reply,
      updateSettings: store.updateSettings,
      refreshProfile: store.refreshProfile,
      retry: store.retry,
      dismissError: store.dismissError,
      clearRuns: store.clearRuns,
      getState: store.getState,
    }),
    [snapshot, store],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
