"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { readAccount, type AccountState } from "./account-state";

export type { AccountState } from "./account-state";

const AccountContext = createContext<AccountState>({ status: "loading" });

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<AccountState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/auth/me", { cache: "no-store", signal: controller.signal })
      .then(readAccount)
      .then(setAccount)
      .catch(() => {
        if (!controller.signal.aborted) setAccount({ status: "off" });
      });
    return () => controller.abort();
  }, []);

  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountState {
  return useContext(AccountContext);
}
