"use client";

import { useQuery } from "@tanstack/react-query";
import { AppShell, AuthGate, EmptyState, VersionFooter } from "@dijione/design-system";
import type { NavSection } from "@dijione/design-system";
import { useBirthdayScope } from "@dijione/auth-client";
import { CakeSlice, LayoutDashboard, ListOrdered, Mail, ShieldCheck, Truck } from "lucide-react";
import { getReleaseMetadata } from "@/lib/api";

function BirthdayContent({ children }: { children: React.ReactNode }) {
  const scope = useBirthdayScope();
  // Genuinely runtime — see /api/meta's own doc comment for why this can't
  // just be a build-time NEXT_PUBLIC_* value like version/gitSha are.
  const { data: releaseMeta } = useQuery({
    queryKey: ["birthday-release-metadata"],
    queryFn: getReleaseMetadata,
    staleTime: 5 * 60_000,
  });

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
        { label: "Dashboard", href: "/", icon: LayoutDashboard, exact: true },
        { label: "Upcoming Birthdays", href: "/upcoming", icon: CakeSlice },
        { label: "Cake Orders", href: "/orders", icon: ListOrdered },
        { label: "Suppliers", href: "/suppliers", icon: Truck },
        { label: "Unmatched Email", href: "/inbound-emails", icon: Mail },
      ],
    },
    // Admin-only, non-production-only. The independent, authoritative
    // enforcement is the backend's require_non_production() (404s the API
    // in PROD regardless of what the nav shows) — this hides the nav item
    // only, per docs/platform/email-architecture.md. is_production comes
    // from /api/meta (runtime, not a NEXT_PUBLIC_* build arg — see that
    // route's own doc comment for why it must not be build-time).
    // Fail-closed on the UI too: requires an explicit `=== false` (not
    // just "not yet true"), so the item stays hidden — briefly, in every
    // environment — until /api/meta has actually confirmed non-production,
    // rather than flashing visible in PROD during the loading state.
    ...(scope.isAdmin && releaseMeta?.is_production === false
      ? [
          {
            label: "Admin",
            items: [{ label: "Email Safety", href: "/admin/email-safety", icon: ShieldCheck }],
          },
        ]
      : []),
  ];

  return (
    <AppShell
      eyebrow="by Dijital Team"
      title="DijiBirthday"
      topNavTitle="Birthday Workflow Automation"
      sections={sections}
      homeHref="/"
      footer={
        <VersionFooter
          appName="DijiBirthday"
          version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
          gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
          releaseDate={releaseMeta?.release_date}
        />
      }
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
