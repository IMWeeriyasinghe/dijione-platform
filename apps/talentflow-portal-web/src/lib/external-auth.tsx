"use client";

import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
} from "react";

/** Client-side session for the Client Talent Review Workspace.
 *
 * There is no login identity here — the magic link IS the credential.
 * `/access#<token>` hands the SPA a raw grant token; it POSTs that to
 * `/api/talent/external/redeem` and gets back a short-lived (≈45 min)
 * session JWT. Both values live in `sessionStorage` only:
 *   - the session JWT is the bearer on every API call;
 *   - the raw token is kept so the SPA can silently re-redeem for a fresh
 *     session when the JWT expires — but ONLY while the grant is still
 *     valid server-side. A revoked/expired grant makes re-redeem fail and
 *     the session ends.
 *
 * Nothing here is trusted for authorization: every `/api/talent/external/*`
 * call is re-authorized server-side against the grant row
 * (`get_talent_external_scope`), and the client scope is resolved there,
 * never from anything this app holds or sends.
 *
 * Read through `useSyncExternalStore` so SSR (`null`) and the first client
 * render agree, and so sign-out in one place re-renders every consumer.
 */

const SESSION_KEY = "dijitalent-external-session";
const RAW_TOKEN_KEY = "dijitalent-external-raw";
const CHANGE_EVENT = "dijitalent-external-session-change";

type ExternalAuthContextValue = {
  session: string | null;
  /** Store a fresh session + the raw token that produced it. */
  establish: (session: string, rawToken: string) => void;
  /** Clear everything — "sign out" / session ended. */
  clear: () => void;
};

const ExternalAuthContext = createContext<ExternalAuthContextValue | null>(null);

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function getClientSnapshot(): string | null {
  return read(SESSION_KEY);
}

function getServerSnapshot(): string | null {
  return null;
}

function writeSession(session: string | null, rawToken?: string | null): void {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, session);
    else sessionStorage.removeItem(SESSION_KEY);
    if (rawToken === null) sessionStorage.removeItem(RAW_TOKEN_KEY);
    else if (rawToken) sessionStorage.setItem(RAW_TOKEN_KEY, rawToken);
  } catch {
    // storage unavailable (private mode etc.) — nothing persists, but the
    // event still drives an in-tab re-render for this session.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Exchange a raw grant token for a session JWT. Returns the JWT, or null
 * for any failure (unknown / expired / revoked grant, rate limited). */
export async function redeemToken(rawToken: string): Promise<string | null> {
  try {
    const res = await fetch("/api/talent/external/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: rawToken }),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { access_token?: string };
    return body.access_token ?? null;
  } catch {
    return null;
  }
}

/** Silent re-redeem using the stored raw token — called by the API layer
 * on a 401. Returns the new session JWT, or null (caller then ends the
 * session). */
export async function refreshSessionFromStoredToken(): Promise<string | null> {
  const raw = read(RAW_TOKEN_KEY);
  if (!raw) return null;
  const session = await redeemToken(raw);
  if (session) {
    writeSession(session, raw);
    return session;
  }
  writeSession(null, null);
  return null;
}

export function currentSession(): string | null {
  return read(SESSION_KEY);
}

export function ExternalAuthProvider({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  const establish = useCallback(
    (next: string, rawToken: string) => writeSession(next, rawToken),
    [],
  );
  const clear = useCallback(() => writeSession(null, null), []);

  return (
    <ExternalAuthContext.Provider value={{ session, establish, clear }}>
      {children}
    </ExternalAuthContext.Provider>
  );
}

export function useExternalAuth() {
  const ctx = useContext(ExternalAuthContext);
  if (!ctx) throw new Error("useExternalAuth must be used within ExternalAuthProvider");
  return ctx;
}
