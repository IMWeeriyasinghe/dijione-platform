"use client";

import { BrandLogo } from "@dijione/design-system";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Briefcase, CalendarClock, LayoutDashboard, LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ExternalAuthProvider, useExternalAuth } from "@/lib/external-auth";

const NAV = [
  { label: "Overview", href: "/", icon: LayoutDashboard },
  { label: "Requests", href: "/requests", icon: Briefcase },
  { label: "Interviews", href: "/interviews", icon: CalendarClock },
];

function NoSession() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-dt-background px-4">
      <div className="w-full max-w-md rounded-2xl border border-dt-border bg-dt-surface p-8 text-center shadow-sm">
        <BrandLogo width={150} className="mx-auto mb-5" />
        <p className="text-xs font-semibold uppercase tracking-wide text-dt-orange">
          Client Talent Review Workspace
        </p>
        <h1 className="mt-2 text-xl font-semibold text-dt-text-primary">
          This workspace is opened from a secure link
        </h1>
        <p className="mt-2 text-sm text-dt-text-secondary">
          Use the access link your Dijital Team contact sent you. If it has expired, ask them
          to send a new one.
        </p>
        <p className="mt-5 text-xs text-dt-text-secondary">Provided by Dijital Team.</p>
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { session, clear } = useExternalAuth();
  const pathname = usePathname();

  // /access manages its own redemption flow and must render with or
  // without a session.
  if (pathname === "/access") return <>{children}</>;
  if (!session) return <NoSession />;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-dt-border bg-dt-surface px-6 py-4">
        <div className="flex items-center gap-3">
          <BrandLogo width={116} />
          <div className="border-l border-dt-border pl-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">
              Dijital Team
            </p>
            <h1 className="text-lg font-semibold text-dt-text-primary">
              Client Talent Review Workspace
            </h1>
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm font-medium text-dt-text-secondary">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="hover:text-dt-text-primary">
              {item.label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          onClick={clear}
          className="flex items-center gap-1.5 rounded-lg border border-dt-border px-3 py-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
        >
          <LogOut className="size-4" />
          Sign out
        </button>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">{children}</main>
      <footer className="px-6 py-4 text-center text-xs text-dt-text-secondary">
        A read-only view of your engagement, provided by Dijital Team.
      </footer>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1 } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <ExternalAuthProvider>
        <Shell>{children}</Shell>
      </ExternalAuthProvider>
    </QueryClientProvider>
  );
}
