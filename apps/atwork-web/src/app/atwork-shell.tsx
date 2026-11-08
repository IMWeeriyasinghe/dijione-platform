"use client";

import { AppShell, AuthGate, EmptyState, ErrorState, LoadingState, VersionFooter } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import { CalendarClock, History, LayoutDashboard, ShieldCheck } from "lucide-react";
import { hasPermission, PERM, useAtworkScope, type AtworkScope } from "@/lib/atwork-scope";

export function buildSections(scope: AtworkScope | null): NavSection[] {
  const sections: NavSection[] = [
    {
      items: [
        { label: "Home", href: "/", icon: LayoutDashboard, exact: true },
        { label: "Today", href: "/today", icon: CalendarClock },
        { label: "My History", href: "/history", icon: History },
      ],
    },
  ];
  if (hasPermission(scope, PERM.ADMIN_AREA)) {
    sections.push({ label: "Admin", items: [{ label: "Administration", href: "/admin", icon: ShieldCheck }] });
  }
  return sections;
}

export function AtworkContent({ children }: { children: React.ReactNode }) {
  const { loading, failed, scope, retry } = useAtworkScope();

  if (loading) return <LoadingState label="Checking access…" />;
  if (failed) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <ErrorState message="DijiAtWork is unavailable right now. Please try again." onRetry={retry} />
      </div>
    );
  }
  if (!scope) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="No DijiAtWork access"
          description="Your account does not hold a DijiAtWork role. Ask a platform administrator for access, or return to DijiOne Home."
          action={
            // Plain <a>: leaves this zone for the shell's own root (no basePath).
            // eslint-disable-next-line @next/next/no-html-link-for-pages
            <a href="/" className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2">
              Back to DijiOne Home
            </a>
          }
        />
      </div>
    );
  }

  return (
    <AppShell
      eyebrow="by Dijital Team"
      title="DijiAtWork"
      topNavTitle="Work Check-in and Attendance"
      sections={buildSections(scope)}
      homeHref="/"
      footer={
        <VersionFooter
          appName="DijiAtWork"
          version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
          gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
        />
      }
    >
      {children}
    </AppShell>
  );
}

export function AtworkShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AtworkContent>{children}</AtworkContent>
    </AuthGate>
  );
}
