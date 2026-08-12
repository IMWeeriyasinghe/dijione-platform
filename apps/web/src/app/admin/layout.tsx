"use client";

import {
  FileClock,
  Grid3x3,
  KeyRound,
  LayoutDashboard,
  ShieldCheck,
  Users as UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { AuthGate } from "@/components/shell/AuthGate";
import { EmptyState } from "@/components/ui/States";
import { usePlatformAdmin } from "@/lib/auth-context";
import type { NavSection } from "@/components/shell/Sidebar";

const ADMIN_SECTIONS: NavSection[] = [
  {
    items: [{ label: "Dashboard", href: "/admin", icon: LayoutDashboard, exact: true }],
  },
  {
    label: "Administration",
    items: [
      { label: "Users", href: "/admin/users", icon: UsersIcon },
      { label: "Applications", href: "/admin/applications", icon: Grid3x3 },
      { label: "Roles", href: "/admin/roles", icon: ShieldCheck },
      { label: "Permissions", href: "/admin/permissions", icon: KeyRound },
      { label: "Client Access", href: "/admin/client-access", icon: UsersIcon },
      { label: "Audit", href: "/admin/audit", icon: FileClock },
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
            <Link href="/" className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2">
              Back to DijiOne Home
            </Link>
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
        <Link
          href="/"
          className="flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/25"
        >
          Back to DijiOne Home
        </Link>
      }
    >
      {children}
    </AppShell>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AdminGate>{children}</AdminGate>
    </AuthGate>
  );
}
