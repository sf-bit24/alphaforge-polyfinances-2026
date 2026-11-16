import { useSyncExternalStore } from "react";

/**
 * Requests in flight, for the loading bar at the top of every screen (`TopLoadingBar`).
 * Background polling (the team's collection runs) is not tracked, so the bar never blinks on its own.
 */
let active = 0;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** Count `work` as a request in flight until it settles; returns it unchanged. */
export function track<T>(work: Promise<T>): Promise<T> {
  active += 1;
  emit();
  return work.finally(() => {
    active -= 1;
    emit();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** True while at least one tracked request is in flight (outside React: tests, logs). */
export function isBusy(): boolean {
  return active > 0;
}

/** True while at least one tracked request is in flight. */
export function useBusy(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => active > 0,
    () => false,
  );
}
