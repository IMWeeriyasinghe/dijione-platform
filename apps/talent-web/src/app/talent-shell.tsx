"use client";

import { AppShell, AuthGate, EmptyState } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import { useTalentScope } from "@dijione/auth-client";
import {
  Briefcase,
  Building2,
  CalendarClock,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Plus,
  Tags,
  Users,
} from "lucide-react";
import Link from "next/link";

function TalentFlowContent({ children }: { children: React.ReactNode }) {
  const scope = useTalentScope();

  if (!scope) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="No DijiTalentFlow access"
          description="This persona does not hold a role in DijiTalentFlow. Switch to a persona with talent access from the user menu, or return to DijiOne Home."
          action={
            // Plain <a>, not next/link: this leaves talent-web's zone
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

  const clientSections: NavSection[] = [
    {
      items: [
        { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
        { label: "My Requests", href: "/requests", icon: Briefcase },
        { label: "Candidates", href: "/candidates", icon: Users },
        { label: "Interviews", href: "/interviews", icon: CalendarClock },
        { label: "Messages", href: "/messages", icon: MessageSquare },
        { label: "Documents", href: "/documents", icon: FileText },
      ],
    },
  ];

  const staffSections: NavSection[] = [
    {
      items: [{ label: "Operations Dashboard", href: "/dashboard", icon: LayoutDashboard }],
    },
    {
      label: "Talent Operations",
      items: [
        { label: "Client Portfolios", href: "/clients", icon: Building2 },
        { label: "All Requests", href: "/requests", icon: Briefcase },
        { label: "Candidate Pool", href: "/candidates", icon: Users },
        { label: "Applications", href: "/applications", icon: FileText },
        { label: "Interview Manager", href: "/interviews", icon: CalendarClock },
        { label: "Recruitment Postings", href: "/postings", icon: Tags },
      ],
    },
  ];

  return (
    <AppShell
      eyebrow="by Dijital Team"
      title="DijiTalentFlow"
      topNavTitle={scope.isStaff ? "Talent Acquisition Workspace" : "Client Workspace"}
      sections={scope.isStaff ? staffSections : clientSections}
      footer={
        !scope.isStaff ? (
          <Link
            href="/requests/new"
            className="flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/25"
          >
            <Plus className="size-4" />
            New Talent Request
          </Link>
        ) : (
          <p className="text-xs text-white/60">DijiTalentFlow · by Dijital Team</p>
        )
      }
    >
      {children}
    </AppShell>
  );
}

export function TalentShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <TalentFlowContent>{children}</TalentFlowContent>
    </AuthGate>
  );
}
