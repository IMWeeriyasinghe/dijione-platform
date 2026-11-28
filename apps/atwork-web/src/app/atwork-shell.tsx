"use client";

import { AppShell, AuthGate, EmptyState, ErrorState, LoadingState, VersionFooter } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";

type NavItem = NavSection["items"][number];
import { BarChart3, CalendarClock, ClipboardCheck, FilePenLine, History, KeyRound, PieChart, ScrollText, Settings, ShieldCheck, Users, UserCheck } from "lucide-react";
import { hasPermission, PERM, useAtworkScope, type AtworkScope } from "@/lib/atwork-scope";

export function buildSections(scope: AtworkScope | null): NavSection[] {
  const can = (key: string) => hasPermission(scope, key);
  const mine: NavItem[] = [];
  if (can(PERM.READ_OWN)) {
    mine.push({ label: "Today", href: "/", icon: CalendarClock, exact: true });
    mine.push({ label: "My Time", href: "/attendance", icon: History });
  }
  if (can(PERM.REQUEST_OWN)) mine.push({ label: "My Requests", href: "/requests", icon: FilePenLine });
  const sections: NavSection[] = mine.length ? [{ items: mine }] : [];
  const hasMgmtAccess = can(PERM.MANAGEMENT) || can(PERM.BP_ACCESS);
  if (hasMgmtAccess) {
    const items: NavItem[] = [{ label: "Overview", href: "/management", icon: ShieldCheck, exact: true }];
    if (can(PERM.READ_ALL) || can(PERM.BP_ACCESS)) items.push({ label: "Employees", href: "/management/employees", icon: Users });
    if (can(PERM.REVIEW)) items.push({ label: "Corrections", href: "/management/corrections", icon: ClipboardCheck });
    if (can(PERM.REPORTS) || can(PERM.BP_ACCESS)) items.push({ label: "Reports", href: "/management/reports", icon: BarChart3 });
    if (can(PERM.READ_ALL) || can(PERM.BP_ACCESS)) items.push({ label: "Analytics", href: "/management/analytics", icon: PieChart });
    if (can(PERM.AUDIT)) items.push({ label: "Audit History", href: "/management/audit", icon: ScrollText });
    if (can(PERM.SETTINGS)) items.push({ label: "Settings", href: "/management/settings", icon: Settings });
    if (can(PERM.ACCESS_MANAGE)) items.push({ label: "Access", href: "/management/access", icon: KeyRound });
    if (can(PERM.ACCESS_MANAGE)) items.push({ label: "BP Access", href: "/management/bp", icon: UserCheck });
    sections.push({ label: "Management", items });
  } else if (can(PERM.ACCESS_MANAGE)) {
    // An access administrator without the Management area sees only Access.
    sections.push({ label: "Management", items: [{ label: "Access", href: "/management/access", icon: KeyRound }] });
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
      roleContext="atwork"
      eyebrow="by Dijital Team"
      title="DijiAtWork"
      topNavTitle="Your Workday, Made Simple"
      sections={buildSections(scope)}
      homeHref="/"
      collapsible={{ storageKey: "atwork.nav.collapsed" }}
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
