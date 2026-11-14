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
import { MobileNav } from "@/components/MobileNav";
import { hasPermission, PERM, useOnsiteScope, type OnsiteScope } from "@/lib/onsite-scope";

export function buildSections(scope: OnsiteScope | null): NavSection[] {
  const sections: NavSection[] = [
    {
      items: [
        { label: "Overview", href: "/", icon: LayoutDashboard, exact: true },
        { label: "Today", href: "/today", icon: CalendarDays },
        { label: "Activity", href: "/activity", icon: Activity },
        { label: "Team Members", href: "/employees", icon: Users },
        { label: "Exceptions", href: "/exceptions", icon: AlertTriangle },
      ],
    },
  ];
  // Each admin page appears only with the permission onsite-api checks for it.
  const admin = [
    hasPermission(scope, PERM.HEALTH) && { label: "Site Health", href: "/admin/health", icon: HeartPulse },
    hasPermission(scope, PERM.IDENTITY) && { label: "Identity Management", href: "/admin/identity", icon: Fingerprint },
    hasPermission(scope, PERM.SITES) && { label: "Sites", href: "/admin/sites", icon: MapPin },
  ].filter((i) => i !== false);
  if (admin.length) sections.push({ label: "Admin", items: admin });
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
      sections={buildSections(scope)}
      homeHref="/"
      footer={
        <VersionFooter
          appName="Diji On-site"
          version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
          gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
        />
      }
    >
      <div className="pb-20 md:pb-0">{children}</div>
      <MobileNav />
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
