"use client";

import {
  Briefcase,
  Building2,
  CalendarClock,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Plus,
  Users,
} from "lucide-react";
import Link from "next/link";
import { AuthGate } from "@/components/shell/AuthGate";
import { AppShell } from "@/components/shell/AppShell";
import { EmptyState } from "@/components/ui/States";
import { useTalentScope } from "@/lib/auth-context";
import type { NavSection } from "@/components/shell/Sidebar";

function TalentFlowContent({ children }: { children: React.ReactNode }) {
  const scope = useTalentScope();

  if (!scope) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <EmptyState
          title="No DijiTalentFlow access"
          description="This persona does not hold a role in DijiTalentFlow. Switch to a persona with talent access from the user menu, or return to DijiOne Home."
          action={
            <Link href="/" className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2">
              Back to DijiOne Home
            </Link>
          }
        />
      </div>
    );
  }

  const clientSections: NavSection[] = [
    {
      items: [
        { label: "Dashboard", href: "/talent-flow/dashboard", icon: LayoutDashboard },
        { label: "My Requests", href: "/talent-flow/requests", icon: Briefcase },
        { label: "Candidates", href: "/talent-flow/candidates", icon: Users },
        { label: "Interviews", href: "/talent-flow/interviews", icon: CalendarClock },
        { label: "Messages", href: "/talent-flow/messages", icon: MessageSquare },
        { label: "Documents", href: "/talent-flow/documents", icon: FileText },
      ],
    },
  ];

  const staffSections: NavSection[] = [
    {
      items: [{ label: "Operations Dashboard", href: "/talent-flow/dashboard", icon: LayoutDashboard }],
    },
    {
      label: "Talent Operations",
      items: [
        { label: "Client Portfolios", href: "/talent-flow/clients", icon: Building2 },
        { label: "All Requests", href: "/talent-flow/requests", icon: Briefcase },
        { label: "Candidate Pool", href: "/talent-flow/candidates", icon: Users },
        { label: "Applications", href: "/talent-flow/applications", icon: FileText },
        { label: "Interview Manager", href: "/talent-flow/interviews", icon: CalendarClock },
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
            href="/talent-flow/requests/new"
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

export default function TalentFlowLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <TalentFlowContent>{children}</TalentFlowContent>
    </AuthGate>
  );
}
