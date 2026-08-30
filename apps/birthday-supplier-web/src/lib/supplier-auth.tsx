"use client";

import { createContext, useCallback, useContext, useSyncExternalStore } from "react";

/** Minimal client-side session for the supplier portal (Phase-Next §6).
 *
 * Production: this app redirects into the Microsoft Entra ID B2B guest
 * OIDC flow and the resulting token is stored here the same way.
 *
 * Local/dry-run: `/login` renders a persona picker backed by birthday-api's
 * dev-only `/api/birthday/internal/dev/supplier-*` endpoints (hard-404s
 * outside development) — the picker chooses *which seeded SupplierUser to
 * become*, never a supplier_id directly. Either path ends the same way:
 * a bearer token whose `supplier` claim birthday-api resolves server-side,
 * kept only in memory/sessionStorage here, never trusted for
 * authorization on the client — every portal API call is re-authorized
 * server-side against that claim.
 *
 * The token is read through `useSyncExternalStore` so the server snapshot
 * (`null`) and the client's first render agree — no hydration mismatch —
 * and so a sign-in/out in one tab (or component) re-renders every consumer.
 */

const STORAGE_KEY = "dijibirthday-supplier-token";
// Same-tab writes don't fire the native `storage` event, so `setToken`
// dispatches this one to notify subscribers in the current tab.
const TOKEN_EVENT = "dijibirthday-supplier-token-change";

type SupplierAuthContextValue = {
  token: string | null;
  setToken: (token: string | null) => void;
  /** Kept for API stability with earlier callers. With useSyncExternalStore
   * the token is correct from the first client render, so this is always
   * true on the client. */
  ready: boolean;
};

const SupplierAuthContext = createContext<SupplierAuthContextValue | null>(null);

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(TOKEN_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(TOKEN_EVENT, onChange);
  };
}

function getClientSnapshot(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function getServerSnapshot(): string | null {
  return null;
}

function writeToken(next: string | null): void {
  try {
    if (next) sessionStorage.setItem(STORAGE_KEY, next);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable (private mode etc.) — nothing persisted, but the
    // event below still drives an in-tab re-render for this session.
  }
  window.dispatchEvent(new Event(TOKEN_EVENT));
}

export function SupplierAuthProvider({ children }: { children: React.ReactNode }) {
  const token = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  const setToken = useCallback((next: string | null) => writeToken(next), []);

  return (
    <SupplierAuthContext.Provider value={{ token, setToken, ready: true }}>
      {children}
    </SupplierAuthContext.Provider>
  );
}

export function useSupplierAuth() {
  const ctx = useContext(SupplierAuthContext);
  if (!ctx) throw new Error("useSupplierAuth must be used within SupplierAuthProvider");
  return ctx;
}
