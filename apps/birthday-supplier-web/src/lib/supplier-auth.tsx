"use client";

import { createContext, useContext, useState } from "react";

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
 */

const STORAGE_KEY = "dijibirthday-supplier-token";

type SupplierAuthContextValue = {
  token: string | null;
  setToken: (token: string | null) => void;
};

const SupplierAuthContext = createContext<SupplierAuthContextValue | null>(null);

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(STORAGE_KEY);
}

export function SupplierAuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(readStoredToken);

  function setToken(next: string | null) {
    setTokenState(next);
    if (next) sessionStorage.setItem(STORAGE_KEY, next);
    else sessionStorage.removeItem(STORAGE_KEY);
  }

  return (
    <SupplierAuthContext.Provider value={{ token, setToken }}>{children}</SupplierAuthContext.Provider>
  );
}

export function useSupplierAuth() {
  const ctx = useContext(SupplierAuthContext);
  if (!ctx) throw new Error("useSupplierAuth must be used within SupplierAuthProvider");
  return ctx;
}
