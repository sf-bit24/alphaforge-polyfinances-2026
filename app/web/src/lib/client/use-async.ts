"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { isAbort, toApiError, type ApiError } from "./api";

interface Loaded<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/**
 * Load data for a key; a new key reloads. While reloading, the previous data stays
 * available (`previous`) so views keep their frame instead of flashing a skeleton.
 */
export function useAsync<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>) {
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const run = useEffectEvent(load);

  useEffect(() => {
    if (key === null) return;
    const controller = new AbortController();
    run(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setLoaded({ key, data, error: null });
      },
      (error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return;
        setLoaded({ key, data: null, error: toApiError(error) });
      },
    );
    return () => controller.abort();
  }, [key]);

  const current = loaded && loaded.key === key ? loaded : null;
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: key !== null && current === null,
    previous: loaded?.data ?? null,
  };
}
