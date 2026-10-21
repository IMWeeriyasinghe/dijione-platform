"use client";

import { AppShell, AuthGate, EmptyState, LoadingState, VersionFooter } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  Fingerprint,
  HeartPulse,
  LayoutDashboard,
  MapPin,
  Users,
} from "lucide-react";
import { useOnsiteScope } from "@/lib/onsite-scope";

export function buildSections(isAdmin: boolean): NavSection[] {
  const sections: NavSection[] = [
    {
      items: [
        { label: "Overview", href: "/", icon: LayoutDashboard, exact: true },
        { label: "Today", href: "/today", icon: CalendarDays },
        { label: "Activity", href: "/activity", icon: Activity },
        { label: "Employees", href: "/employees", icon: Users },
        { label: "Exceptions", href: "/exceptions", icon: AlertTriangle },
      ],
    },
  ];
  if (isAdmin) {
    sections.push({
      label: "Admin",
      items: [
        { label: "Site Health", href: "/admin/health", icon: HeartPulse },
        { label: "Identity Match", href: "/admin/identity", icon: Fingerprint },
        { label: "Sites", href: "/admin/sites", icon: MapPin },
      ],
    });
  }
  return sections;
}

export function OnsiteContent({ children }: { children: React.ReactNode }) {
  const { loading, scope } = useOnsiteScope();

  if (loading) return <LoadingState label="Checking access…" />;
  if (!scope) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="No Diji On-site access"
          description="Your account does not hold a Diji On-site role. Ask a platform administrator for access, or return to DijiOne Home."
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
      title="Diji On-site"
      topNavTitle="On-site Attendance Operations"
      sections={buildSections(scope.isAdmin)}
      homeHref="/"
      footer={
        <VersionFooter
          appName="Diji On-site"
          version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
          gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
        />
      }
    >
      {children}
    </AppShell>
  );
}

export function OnsiteShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <OnsiteContent>{children}</OnsiteContent>
    </AuthGate>
  );
}
