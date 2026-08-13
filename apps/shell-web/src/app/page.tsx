"use client";

import { AppShell, AuthGate, Button, Card, EmptyState, ErrorState, LoadingState, formatDateTime } from "@dijione/design-system";
import { listNotifications, useAuth, usePlatformAdmin } from "@dijione/auth-client";
import { useQuery } from "@tanstack/react-query";
import { Home, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { AttentionPanel } from "@/components/home/AttentionPanel";
import { ModuleCard } from "@/components/home/ModuleCard";
import { PlatformHealth } from "@/components/home/PlatformHealth";
import { listModules } from "@/lib/api";

const RECENT_ACTIVITY_LIMIT = 5;
const RECENT_ACTIVITY_EXPANDED_LIMIT = 20;

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function HomeContent() {
  const { user } = useAuth();
  const isPlatformAdmin = usePlatformAdmin();
  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: listModules });
  const activityQuery = useQuery({ queryKey: ["notifications"], queryFn: () => listNotifications() });
  const [activityExpanded, setActivityExpanded] = useState(false);

  const firstName = user?.full_name.split(" ")[0] ?? "";

  // Active modules first, coming-soon modules pushed to the end — keeps the
  // grid's visual priority on what's actually usable today.
  const sortedModules = modulesQuery.data
    ? [...modulesQuery.data].sort((a, b) => {
        const aComingSoon = a.status === "COMING_SOON" ? 1 : 0;
        const bComingSoon = b.status === "COMING_SOON" ? 1 : 0;
        return aComingSoon - bComingSoon || a.display_order - b.display_order;
      })
    : [];

  const navItems = [{ label: "DijiOne Home", href: "/", icon: Home, exact: true, external: false }];
  if (isPlatformAdmin) {
    // Proxied to admin-web (a separate Next.js zone) — must be a full
    // navigation, not a client-side transition (see NavItem.external).
    navItems.push({ label: "Administration", href: "/admin", icon: ShieldCheck, exact: false, external: true });
  }

  return (
    <AppShell
      eyebrow="Dijital Team"
      title="DijiOne"
      topNavTitle="DijiOne Home"
      sections={[{ items: navItems }]}
      footer={<p className="text-xs text-white/60">DijiOne · by Dijital Team</p>}
    >
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-dt-text-primary">
          {greeting()}, {firstName}.
        </h1>
        <p className="mt-1 text-sm text-dt-text-secondary">Here is what needs your attention today.</p>
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
          My Apps
        </h2>
        {modulesQuery.isLoading && <LoadingState label="Loading your apps…" />}
        {modulesQuery.isError && (
          <ErrorState message="Could not load DijiOne modules." onRetry={() => modulesQuery.refetch()} />
        )}
        {modulesQuery.data && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sortedModules.map((m) => (
              <ModuleCard key={m.key} module={m} />
            ))}
          </div>
        )}
      </section>

      {modulesQuery.data && <AttentionPanel modules={modulesQuery.data} />}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
              Recent Activity
            </h2>
            {activityQuery.data && activityQuery.data.length > RECENT_ACTIVITY_LIMIT && (
              <Button variant="ghost" size="sm" onClick={() => setActivityExpanded((v) => !v)}>
                {activityExpanded ? "Show less" : "View All"}
              </Button>
            )}
          </div>
          <Card className="p-2">
            {activityQuery.isLoading && <LoadingState label="Loading activity…" />}
            {activityQuery.data && activityQuery.data.length === 0 && (
              <EmptyState title="No recent activity" description="Platform events will show up here." />
            )}
            {activityQuery.data && activityQuery.data.length > 0 && (
              <ul className="divide-y divide-dt-border">
                {activityQuery.data
                  .slice(0, activityExpanded ? RECENT_ACTIVITY_EXPANDED_LIMIT : RECENT_ACTIVITY_LIMIT)
                  .map((n) => (
                    <li key={n.id} className="flex items-start gap-3 px-3 py-3">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-dt-orange" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-dt-text-primary">{n.title}</p>
                          {n.related_entity_type && (
                            <span className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-dt-text-secondary">
                              {n.related_entity_type.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        {n.body && <p className="text-sm text-dt-text-secondary">{n.body}</p>}
                        <p className="mt-0.5 text-xs text-dt-text-secondary/70">{formatDateTime(n.created_at)}</p>
                      </div>
                    </li>
                  ))}
              </ul>
            )}
          </Card>
        </section>

        <section className="flex flex-col gap-6">
          <div>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
              Platform Health
            </h2>
            {modulesQuery.data && <PlatformHealth modules={modulesQuery.data} />}
          </div>

          <div>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
              Ask DijiOne
            </h2>
            <Card className="flex items-start gap-3 bg-linear-to-br from-dt-red-deep to-dt-burnt-orange p-4 text-white">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-white/15">
                <Sparkles className="size-4" />
              </div>
              <div>
                <p className="text-sm font-semibold">Coming soon</p>
                <p className="mt-0.5 text-xs text-white/85">
                  Ask questions across your modules once Microsoft Copilot / Cowork is wired in.
                </p>
              </div>
            </Card>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

export default function DijiOneHomePage() {
  return (
    <AuthGate>
      <HomeContent />
    </AuthGate>
  );
}
