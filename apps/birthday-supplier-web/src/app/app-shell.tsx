"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { BrandLogo, VersionFooter } from "@dijione/design-system";
import { SupplierAuthProvider, useSupplierAuth } from "@/lib/supplier-auth";
import { usePortalMe } from "@/lib/portal-me";
import { LoginScreen } from "./login-screen";

function Shell({ children }: { children: React.ReactNode }) {
  // `token` comes from useSyncExternalStore: the first client render uses the
  // server snapshot (null) to match SSR, then re-renders with the stored
  // token — so there is no hydration mismatch and no flash to guard against.
  const { token, setToken } = useSupplierAuth();
  const me = usePortalMe();

  if (!token) return <LoginScreen />;

  return (
    <div className="flex min-h-screen flex-col">
      {me?.read_only && (
        <div className="sticky top-0 z-40 bg-dt-burnt-orange px-6 py-2 text-center text-sm font-medium text-white">
          Viewing as {me.user_name || "supplier user"} — read-only internal preview. Sign out to exit.
        </div>
      )}
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-dt-border bg-dt-surface px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-3">
          <BrandLogo width={110} className="shrink-0" />
          <div className="hidden border-l border-dt-border pl-3 sm:block">
            <p className="text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">
              DijiBirthday · by Dijital Team
            </p>
            <h1 className="text-lg font-semibold text-dt-text-primary">Supplier Portal</h1>
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm font-medium text-dt-text-secondary">
          <Link href="/" className="hover:text-dt-text-primary">
            Dashboard
          </Link>
          <Link href="/orders" className="hover:text-dt-text-primary">
            Orders
          </Link>
        </nav>
        <button
          type="button"
          onClick={() => setToken(null)}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-dt-border px-3 py-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
        >
          <LogOut className="size-4" />
          Sign out
        </button>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t border-dt-border bg-dt-surface px-4 py-3 sm:px-6">
        <VersionFooter appLabel="Supplier Portal" tone="light" />
      </footer>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } })
  );
  return (
    <QueryClientProvider client={client}>
      <SupplierAuthProvider>
        <Shell>{children}</Shell>
      </SupplierAuthProvider>
    </QueryClientProvider>
  );
}
