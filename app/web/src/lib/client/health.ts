"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { GatewayHealth, Locale } from "@/lib/contract/schemas";
import { getHealth } from "./api";

interface HealthSnapshot {
  status: "idle" | "loading" | "ready" | "error";
  health: GatewayHealth | null;
}

const IDLE: HealthSnapshot = { status: "idle", health: null };
let snapshot: HealthSnapshot = IDLE;
const listeners = new Set<() => void>();

function set(next: HealthSnapshot) {
  snapshot = next;
  for (const listener of listeners) listener();
}

function load(locale: Locale) {
  if (snapshot.status !== "idle") return;
  set({ status: "loading", health: null });
  getHealth({ locale, messages: { network: "network", invalidResponse: "invalid", noResult: "none" } })
    .then((health) => set({ status: "ready", health }))
    .catch(() => set({ status: "error", health: null }));
}

/** Mode of the gateway and health of the runtime, fetched once per page load. */
export function useHealth(locale: Locale): HealthSnapshot {
  const value = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot,
    () => IDLE,
  );
  useEffect(() => load(locale), [locale]);
  return value;
}
