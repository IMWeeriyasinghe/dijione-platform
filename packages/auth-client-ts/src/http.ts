// Every DijiOne frontend app fetches relative paths only (e.g.
// "/api/talent/requests") — there is no per-app API_BASE_URL anymore.
// Each app's next.config.ts rewrites those paths to the right backend
// service (or, when the app is loaded through shell-web's gateway, the
// browser never even leaves shell-web's origin). See
// docs/platform/service-contracts.md "Gateway / routing".

const TOKEN_STORAGE_KEY = "dijione.devToken";

/** The administrator's own (staff) session token, never the View-as token. */
export function getStaffToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

// A read-only View-as session lives in sessionStorage, so it belongs to this tab alone and ends with it.
// While it exists every request carries its token instead of the staff token; the staff token is left
// untouched in localStorage and is back in use the moment the View-as session ends.
const VIEW_AS_STORAGE_KEY = "dijione.viewAs";

export type ViewAsSessionData = {
  token: string;
  sessionId: string;
  targetName: string;
  targetEmail: string;
  expiresAt: string;
  returnTo: string;
};

export function getViewAsSession(): ViewAsSessionData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(VIEW_AS_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as ViewAsSessionData;
    if (!data.token || Date.parse(data.expiresAt) <= Date.now()) {
      window.sessionStorage.removeItem(VIEW_AS_STORAGE_KEY);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function setViewAsSession(data: ViewAsSessionData | null) {
  if (typeof window === "undefined") return;
  if (data) window.sessionStorage.setItem(VIEW_AS_STORAGE_KEY, JSON.stringify(data));
  else window.sessionStorage.removeItem(VIEW_AS_STORAGE_KEY);
}

/** Fired in this tab when a View-as session ends without the person asking (expired, ended elsewhere, access changed). */
export const VIEW_AS_ENDED_EVENT = "dijione:view-as-ended";

/** Drops this tab's View-as session and tells listeners; the staff session is not touched. */
export function endViewAsLocally() {
  setViewAsSession(null);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(VIEW_AS_ENDED_EVENT));
}

export function getToken(): string | null {
  return getViewAsSession()?.token ?? getStaffToken();
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
  if (getViewAsSession()) return Promise.resolve(false);
  inflightRefresh ??= (async () => {
    try {
      const res = await fetch(REFRESH_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenAtStart}` },
      });
      if (res.status === 401) {
        // Only end the session this refresh belonged to; a newer sign-in must not be cleared.
        if (getToken() === tokenAtStart) {
          setToken(null);
          if (typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
        }
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

/** A 401 on a View-as request means the session is over (ended, expired, or access changed). */
function noteViewAsEnded(res: Response) {
  if (res.status === 401 && getViewAsSession()) endViewAsLocally();
}

function revokedAndRefreshable(
  res: Response, token: string | null, path: string, retried: boolean, inViewAs: boolean,
): boolean {
  return (
    res.status === 401 &&
    !inViewAs && // a View-as token cannot be refreshed: it simply ends
    !!token &&
    !retried &&
    path !== REFRESH_PATH &&
    res.headers?.get("X-Auth-Error") === "session_revoked"
  );
}

/**
 * ``fetch`` with the session token attached, for the places that need the raw Response
 * (downloads, uploads, images). Like ``request`` it re-issues the token once and repeats the
 * call when the server says the session was revoked.
 */
export async function authorizedFetch(path: string, init: RequestInit = {}, retried = false): Promise<Response> {
  const token = getToken();
  const inViewAs = getViewAsSession() !== null; // read before the response can end the session
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  noteViewAsEnded(res);
  if (revokedAndRefreshable(res, token, path, retried, inViewAs) && (await refreshTokenOnce(token as string))) {
    return authorizedFetch(path, init, true);
  }
  return res;
}

export async function request<T>(path: string, options: RequestInit = {}, retriedAfterRevocation = false): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const inViewAs = getViewAsSession() !== null; // read before the response can end the session
  const res = await fetch(path, { ...options, headers });
  noteViewAsEnded(res);

  // The server revoked this session because the person's access changed. Re-issue
  // the token and repeat the request once; a second revocation is an error, not a loop.
  if (revokedAndRefreshable(res, token, path, retriedAfterRevocation, inViewAs) && (await refreshTokenOnce(token as string))) {
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
