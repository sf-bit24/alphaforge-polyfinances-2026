"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Sent after `history.replaceState`, which does not fire `hashchange`. */
const HASH_REPLACED = "alphaforge:hash-replaced";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  window.addEventListener(HASH_REPLACED, onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener(HASH_REPLACED, onChange);
  };
}

/**
 * The tab named by the URL fragment (`/knowledge#graph`), or `fallback`. Choosing a tab rewrites
 * the fragment without a history entry, so a reload or a shared link opens the same tab. The
 * server render, and the first client render, show `fallback`.
 */
export function useHashTab<T extends string>(tabs: readonly T[], fallback: T): [T, (tab: T) => void] {
  const read = useCallback(() => {
    const fragment = window.location.hash.slice(1);
    return (tabs as readonly string[]).includes(fragment) ? (fragment as T) : fallback;
  }, [tabs, fallback]);
  const tab = useSyncExternalStore(subscribe, read, () => fallback);
  const select = useCallback(
    (next: T) => {
      const { pathname, search } = window.location;
      window.history.replaceState(window.history.state, "", next === fallback ? `${pathname}${search}` : `#${next}`);
      window.dispatchEvent(new Event(HASH_REPLACED));
    },
    [fallback],
  );
  return [tab, select];
}
