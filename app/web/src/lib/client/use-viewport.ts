"use client";

import { useSyncExternalStore } from "react";

export interface Viewport {
  width: number;
  height: number;
}

/** Rendered on the server and during hydration; the real size follows on the client. */
const SERVER: Viewport = { width: 1440, height: 900 };
let current: Viewport = SERVER;

function read(): Viewport {
  if (current.width !== window.innerWidth || current.height !== window.innerHeight) {
    current = { width: window.innerWidth, height: window.innerHeight };
  }
  return current;
}

function subscribe(listener: () => void): () => void {
  window.addEventListener("resize", listener);
  return () => window.removeEventListener("resize", listener);
}

/** Window size, for screens drawn in window coordinates (the journey scene). */
export function useViewport(): Viewport {
  return useSyncExternalStore(subscribe, read, () => SERVER);
}
