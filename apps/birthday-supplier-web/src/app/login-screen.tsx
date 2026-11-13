"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { BrandLogo } from "@dijione/design-system";
import {
  devSupplierLogin,
  getSupplierAuthConfig,
  listDevSupplierPersonas,
} from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

/**
 * Supplier Portal sign-in. The UI is chosen from birthday-api's
 * `/api/birthday/supplier/auth/config` (`supplier_auth_mode`):
 *
 *  - `entra` (hosted DEV) — a single "Sign in with Microsoft" button that
 *    navigates to `/login`, which runs the Entra B2B guest Authorization
 *    Code + PKCE flow. No "development mode" wording.
 *  - `dev` (local) — the seeded `SupplierUser` persona picker, backed by
 *    birthday-api's dev-only endpoints (which 404 under `entra`).
 *
 * A failed config call falls back to the persona picker; that path is
 * itself gated server-side, so nothing is exposed by the fallback.
 */
export function LoginScreen() {
  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ["supplier-auth-config"],
    queryFn: getSupplierAuthConfig,
    retry: false,
  });

  if (configLoading) {
    return (
      <Frame>
        <p className="mt-4 text-sm text-dt-text-secondary">Loading…</p>
      </Frame>
    );
  }

  return config?.supplier_auth_mode === "entra" ? <EntraSignIn /> : <DevPersonaPicker />;
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-dt-border bg-dt-surface p-8 shadow-sm">
        <BrandLogo width={140} className="mb-4" />
        <p className="text-xs font-semibold uppercase tracking-wide text-dt-orange">
          DijiBirthday · by Dijital Team
        </p>
        <h1 className="mt-1 text-xl font-semibold text-dt-text-primary">Supplier Portal Sign-in</h1>
        {children}
      </div>
    </div>
  );
}

function EntraSignIn() {
  // AppShell swaps LoginScreen in for `children` without ever navigating
  // away from the requested URL (e.g. an email's /orders/123 deep link),
  // so the current pathname here IS the page the supplier actually meant
  // to reach — pass it through so /login can carry it across the Entra
  // round trip and land the supplier back on it, not the portal home.
  const pathname = usePathname();
  const loginHref =
    pathname && pathname !== "/" ? `/login?return_to=${encodeURIComponent(pathname)}` : "/login";

  return (
    <Frame>
      <p className="mt-2 text-sm text-dt-text-secondary">
        Sign in with the Microsoft account your organisation was invited with.
      </p>
      <a
        href={loginHref}
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-dt-burnt-orange px-4 py-2.5 text-sm font-medium text-white transition hover:bg-dt-orange-deep"
      >
        Sign in with Microsoft
      </a>
      <p className="mt-4 text-xs text-dt-text-secondary">
        Access is granted per supplier — a valid Microsoft account that has not been
        registered as a supplier contact will not be able to enter the portal.
      </p>
    </Frame>
  );
}

function DevPersonaPicker() {
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
    <Frame>
      <p className="mt-2 text-sm text-dt-text-secondary">
        Local development mode — pick a supplier persona below. Hosted environments use
        Microsoft Entra ID sign-in.
      </p>

      <div className="mt-6 flex flex-col gap-2">
        {isLoading && <p className="text-sm text-dt-text-secondary">Loading personas…</p>}
        {isError && (
          <p className="text-sm text-dt-danger">
            No dev personas available. This screen only works with SUPPLIER_AUTH_MODE=dev, and at
            least one SupplierUser must exist.
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
    </Frame>
  );
}
