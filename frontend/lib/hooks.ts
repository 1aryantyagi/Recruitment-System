"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./auth";

/** Redirect to /login when there is no authenticated session. */
export function useRequireAuth() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  return { user, loading, authed: !!user };
}

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Generic client-side fetch hook with loading / error state.
 * The fetcher is called with an AbortSignal; pass a stable list of `deps`.
 */
export function useFetch<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean } = {},
): FetchState<T> {
  const enabled = options.enabled ?? true;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetcherRef.current(controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) setData(res);
      })
      .catch((e: Error) => {
        if (controller.signal.aborted || e.name === "AbortError") return;
        setError(e.message || "Something went wrong");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, enabled, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, reload };
}

/** Debounce a fast-changing value (e.g. search input). */
export function useDebounce<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
