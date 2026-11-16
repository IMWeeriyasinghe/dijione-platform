// Every DijiOne frontend app fetches relative paths only (e.g.
// "/api/talent/requests") — there is no per-app API_BASE_URL anymore.
// Each app's next.config.ts rewrites those paths to the right backend
// service (or, when the app is loaded through shell-web's gateway, the
// browser never even leaves shell-web's origin). See
// docs/platform/service-contracts.md "Gateway / routing".

const TOKEN_STORAGE_KEY = "dijione.devToken";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Fired when the server ends the session (an inactive account, or a refresh that is refused). */
export const SESSION_ENDED_EVENT = "dijione:session-ended";

const REFRESH_PATH = "/api/auth/refresh";
let inflightRefresh: Promise<boolean> | null = null;

/**
 * Re-issue the session token once, shared by every request that needs it. Returns
 * true when a current token is now stored. A 401 means the session is over: the
 * token is dropped and listeners are told. Any other failure leaves the token as is.
 */
export function refreshTokenOnce(tokenAtStart: string): Promise<boolean> {
  inflightRefresh ??= (async () => {
    try {
      const res = await fetch(REFRESH_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenAtStart}` },
      });
      if (res.status === 401) {
        if (getToken() === tokenAtStart) setToken(null);
        if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
        return false;
      }
      if (!res.ok) return false;
      const body = await res.json();
      if (getToken() === tokenAtStart) setToken(body.access_token);
      return true;
    } catch {
      return false;
    } finally {
      inflightRefresh = null;
    }
  })();
  return inflightRefresh;
}

export async function request<T>(path: string, options: RequestInit = {}, retriedAfterRevocation = false): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });

  // The server revoked this session because the person's access changed. Re-issue
  // the token and repeat the request once; a second revocation is an error, not a loop.
  if (
    res.status === 401 &&
    token &&
    !retriedAfterRevocation &&
    path !== REFRESH_PATH &&
    res.headers?.get("X-Auth-Error") === "session_revoked" &&
    (await refreshTokenOnce(token))
  ) {
    return request<T>(path, options, true);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}
