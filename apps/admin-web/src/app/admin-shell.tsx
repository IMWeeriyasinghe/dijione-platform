"use client";

import { usePlatformAdmin } from "@dijione/auth-client";
import { AppShell, AuthGate, EmptyState } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import {
  BookOpen,
  FileClock,
  Grid3x3,
  KeyRound,
  LayoutDashboard,
  ShieldCheck,
  UsersRound,
  Users as UsersIcon,
} from "lucide-react";

// Hrefs are relative to this app's basePath ("/admin", set in next.config.ts)
// — Next.js prepends it automatically, so "/" here really means "/admin".
const ADMIN_SECTIONS: NavSection[] = [
  {
    items: [{ label: "Dashboard", href: "/", icon: LayoutDashboard, exact: true }],
  },
  {
    label: "Administration",
    items: [
      { label: "Users", href: "/users", icon: UsersIcon },
      { label: "Applications", href: "/applications", icon: Grid3x3 },
      { label: "Groups", href: "/groups", icon: UsersRound },
      { label: "Roles", href: "/roles", icon: ShieldCheck },
      { label: "Permissions", href: "/permissions", icon: KeyRound },
      { label: "Client Access", href: "/client-access", icon: UsersIcon },
      { label: "Guide & Access Model", href: "/guide", icon: BookOpen },
      { label: "Audit", href: "/audit", icon: FileClock },
    ],
  },
];

function AdminGate({ children }: { children: React.ReactNode }) {
  const isPlatformAdmin = usePlatformAdmin();

  if (!isPlatformAdmin) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="Administration access required"
          description="This persona does not hold SUPER_ADMIN or PLATFORM_ADMIN privileges. Switch to an admin persona from the user menu, or return to DijiOne Home."
          icon={ShieldCheck}
          action={
            // Plain <a>, not next/link: this leaves admin-web's zone
            // entirely (back to the shell's own root), so it must not be
            // prefixed with this app's basePath.
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
      eyebrow="DijiOne"
      title="Admin Center"
      topNavTitle="DijiOne Admin"
      sections={ADMIN_SECTIONS}
      footer={
        // eslint-disable-next-line @next/next/no-html-link-for-pages -- cross-zone escape, see above
        <a
          href="/"
          className="flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/25"
        >
          Back to DijiOne Home
        </a>
      }
    >
      {children}
    </AppShell>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AdminGate>{children}</AdminGate>
    </AuthGate>
  );
}
