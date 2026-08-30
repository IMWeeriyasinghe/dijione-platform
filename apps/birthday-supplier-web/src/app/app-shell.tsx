"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { SupplierAuthProvider, useSupplierAuth } from "@/lib/supplier-auth";
import { LoginScreen } from "./login-screen";

function Shell({ children }: { children: React.ReactNode }) {
  // `token` comes from useSyncExternalStore: the first client render uses the
  // server snapshot (null) to match SSR, then re-renders with the stored
  // token — so there is no hydration mismatch and no flash to guard against.
  const { token, setToken } = useSupplierAuth();

  if (!token) return <LoginScreen />;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-dt-border bg-dt-surface px-6 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">
            DijiBirthday · by Dijital Team
          </p>
          <h1 className="text-lg font-semibold text-dt-text-primary">Supplier Portal</h1>
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
          className="flex items-center gap-1.5 rounded-lg border border-dt-border px-3 py-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
        >
          <LogOut className="size-4" />
          Sign out
        </button>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">{children}</main>
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
