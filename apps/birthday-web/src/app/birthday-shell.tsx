"use client";

import { AppShell, AuthGate, EmptyState } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import { useBirthdayScope } from "@dijione/auth-client";
import { CakeSlice, LayoutDashboard, ListOrdered, Truck } from "lucide-react";

function BirthdayContent({ children }: { children: React.ReactNode }) {
  const scope = useBirthdayScope();

  if (!scope) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="No DijiBirthday access"
          description="This persona does not hold a role in DijiBirthday. Switch to a persona with birthday access from the user menu, or return to DijiOne Home."
          action={
            // Plain <a>, not next/link: this leaves birthday-web's zone
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

  const sections: NavSection[] = [
    {
      items: [
        { label: "Dashboard", href: "/", icon: LayoutDashboard },
        { label: "Upcoming Birthdays", href: "/upcoming", icon: CakeSlice },
        { label: "Cake Orders", href: "/orders", icon: ListOrdered },
        { label: "Suppliers", href: "/suppliers", icon: Truck },
      ],
    },
  ];

  return (
    <AppShell
      eyebrow="by Dijital Team"
      title="DijiBirthday"
      topNavTitle="Birthday Workflow Automation"
      sections={sections}
      footer={<p className="text-xs text-white/60">DijiBirthday · by Dijital Team</p>}
    >
      {children}
    </AppShell>
  );
}

export function BirthdayShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <BirthdayContent>{children}</BirthdayContent>
    </AuthGate>
  );
}
