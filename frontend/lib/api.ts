// Typed fetch client for the Recruitment ATS backend.
//
// - Token persisted in localStorage under "ats_token".
// - request<T> adds the Bearer header, builds the query string, unwraps `.data`,
//   and throws Error(message) on non-2xx responses using the API error envelope.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "ats_token";
const REFRESH_KEY = "ats_refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setRefreshToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(REFRESH_KEY, token);
}

/** Persist a fresh access (+ optional refresh) pair, e.g. after login/refresh. */
export function setTokens(accessToken: string, refreshToken?: string): void {
  setToken(accessToken);
  if (refreshToken) setRefreshToken(refreshToken);
}

/** Clear the whole session (access + refresh). */
export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

// De-duped refresh: concurrent 401s share one in-flight /auth/refresh call.
let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const rt = getRefreshToken();
  if (!rt) return false;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        clearToken(); // refresh token dead/revoked → force re-login
        return false;
      }
      const json = await res.json();
      const data = (json?.data ?? json) as {
        access_token?: string;
        refresh_token?: string;
      };
      if (data?.access_token) {
        setTokens(data.access_token, data.refresh_token);
        return true;
      }
      clearToken();
      return false;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

/** fetch() with the Bearer access token; on a 401, transparently rotates the
 *  refresh token once and retries the original request. */
async function fetchWithAuth(
  url: string,
  init: RequestInit,
  allowRetry = true,
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(url, { ...init, headers });

  // Don't auto-refresh for the login/refresh endpoints themselves.
  const isAuthExchange =
    url.includes("/auth/login") || url.includes("/auth/refresh");
  if (res.status === 401 && allowRetry && !isAuthExchange && getRefreshToken()) {
    const refreshed = await tryRefresh();
    if (refreshed) return fetchWithAuth(url, init, false);
  }
  return res;
}

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue | QueryValue[]>;

function buildQuery(query?: QueryParams): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) {
        if (v === null || v === undefined || v === "") continue;
        params.append(key, String(v));
      }
    } else {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export interface ApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;
}

function makeError(
  message: string,
  status: number,
  code?: string,
  detail?: unknown,
): ApiError {
  const err = new Error(message) as ApiError;
  err.status = status;
  err.code = code;
  err.detail = detail;
  return err;
}

interface RequestOptions {
  method?: string;
  body?: unknown; // serialised to JSON unless it is FormData
  query?: QueryParams;
  signal?: AbortSignal;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const headers: Record<string, string> = {};

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body; // browser sets multipart boundary
  } else if (body !== undefined && body !== null) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const url = `${API_BASE}${path}${buildQuery(query)}`;

  let res: Response;
  try {
    res = await fetchWithAuth(url, { method, headers, body: payload, signal });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw makeError(
      "Cannot reach the server. Is the API running?",
      0,
      "NETWORK_ERROR",
    );
  }

  // Handle empty bodies (204 etc.)
  const text = await res.text();
  let json: unknown = undefined;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      json = undefined;
    }
  }

  if (!res.ok) {
    const envelope = json as
      | { error?: { code?: string; message?: string; detail?: unknown } }
      | undefined;
    const apiErr = envelope?.error;
    const message =
      apiErr?.message ||
      (res.status === 401
        ? "Your session has expired. Please log in again."
        : `Request failed (${res.status})`);
    throw makeError(message, res.status, apiErr?.code, apiErr?.detail);
  }

  // Unwrap `.data` envelope when present.
  if (json && typeof json === "object" && "data" in json) {
    return (json as { data: T }).data;
  }
  return json as T;
}

// ---- Convenience helpers ----

export function apiGet<T>(
  path: string,
  query?: QueryParams,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(path, { method: "GET", query, signal });
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  query?: QueryParams,
): Promise<T> {
  return request<T>(path, { method: "POST", body, query });
}

export function apiPatch<T>(
  path: string,
  body?: unknown,
  query?: QueryParams,
): Promise<T> {
  return request<T>(path, { method: "PATCH", body, query });
}

export function apiDelete<T>(
  path: string,
  body?: unknown,
  query?: QueryParams,
): Promise<T> {
  return request<T>(path, { method: "DELETE", body, query });
}

export function apiUpload<T>(
  path: string,
  formData: FormData,
  method = "POST",
): Promise<T> {
  return request<T>(path, { method, body: formData });
}

/** Raw list-envelope request (keeps total/page/limit metadata). */
export async function apiList<T>(
  path: string,
  query?: QueryParams,
  signal?: AbortSignal,
): Promise<{
  data: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}> {
  const url = `${API_BASE}${path}${buildQuery(query)}`;

  let res: Response;
  try {
    res = await fetchWithAuth(url, { method: "GET", signal });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw makeError(
      "Cannot reach the server. Is the API running?",
      0,
      "NETWORK_ERROR",
    );
  }

  const text = await res.text();
  const json = text ? JSON.parse(text) : {};

  if (!res.ok) {
    const apiErr = (json as { error?: { code?: string; message?: string } })
      ?.error;
    throw makeError(
      apiErr?.message || `Request failed (${res.status})`,
      res.status,
      apiErr?.code,
    );
  }

  const env = json as {
    data?: T[];
    total?: number;
    page?: number;
    limit?: number;
    total_pages?: number;
  };
  return {
    data: env.data ?? [],
    total: env.total ?? 0,
    page: env.page ?? 1,
    limit: env.limit ?? 20,
    total_pages: env.total_pages ?? 1,
  };
}
