"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { devSupplierLogin, listDevSupplierPersonas } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

/** Production entry point: redirect into the Microsoft Entra ID B2B guest
 * OIDC flow (not implemented in this dry-run phase — the app registration
 * and tenant configuration are a separate rollout step). Until then, and
 * for all local/dry-run testing, this renders the dev-only supplier
 * persona picker — hard-disabled server-side outside development
 * (birthday-api's `/api/birthday/internal/dev/*` 404s when
 * `APP_ENV=production`), so this screen simply has nothing to show in
 * production rather than needing its own environment check. */
export function LoginScreen() {
  const { setToken } = useSupplierAuth();
  const [loggingIn, setLoggingIn] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: personas, isLoading, isError } = useQuery({
    queryKey: ["dev-supplier-personas"],
    queryFn: listDevSupplierPersonas,
    retry: false,
  });

  async function handleLogin(supplierUserId: number) {
    setLoggingIn(supplierUserId);
    setError(null);
    try {
      const { access_token } = await devSupplierLogin(supplierUserId);
      setToken(access_token);
    } catch {
      setError("Sign-in failed. This persona may no longer exist.");
    } finally {
      setLoggingIn(null);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-dt-border bg-dt-surface p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-dt-burnt-orange">
          DijiBirthday · by Dijital Team
        </p>
        <h1 className="mt-1 text-xl font-semibold text-dt-text-primary">Supplier Portal Sign-in</h1>
        <p className="mt-2 text-sm text-dt-text-secondary">
          Production sign-in uses Microsoft Entra ID (organizational guest access). This
          environment is running in development mode — pick a supplier persona below.
        </p>

        <div className="mt-6 flex flex-col gap-2">
          {isLoading && <p className="text-sm text-dt-text-secondary">Loading personas…</p>}
          {isError && (
            <p className="text-sm text-dt-danger">
              No dev personas available. This screen only works outside production, and at least
              one SupplierUser must exist.
            </p>
          )}
          {personas?.length === 0 && (
            <p className="text-sm text-dt-text-secondary">
              No supplier users found. Ask an internal admin to create one.
            </p>
          )}
          {personas?.map((p) => (
            <button
              key={p.supplier_user_id}
              type="button"
              disabled={loggingIn !== null}
              onClick={() => handleLogin(p.supplier_user_id)}
              className="flex flex-col items-start rounded-lg border border-dt-border px-4 py-3 text-left hover:border-dt-orange disabled:opacity-50"
            >
              <span className="text-sm font-medium text-dt-text-primary">{p.full_name}</span>
              <span className="text-xs text-dt-text-secondary">
                {p.supplier_name} · {p.email}
              </span>
            </button>
          ))}
        </div>

        {error && <p className="mt-4 text-sm text-dt-danger">{error}</p>}
      </div>
    </div>
  );
}
