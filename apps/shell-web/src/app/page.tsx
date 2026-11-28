"use client";

import { AppShell, AuthGate, Button, Card, EmptyState, ErrorState, LoadingState, VersionFooter, formatDateTime } from "@dijione/design-system";
import { listNotifications, useAuth, usePlatformAdmin } from "@dijione/auth-client";
import { useQuery } from "@tanstack/react-query";
import { Home, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { AttentionPanel } from "@/components/home/AttentionPanel";
import { AppSearch } from "@/components/home/AppSearch";
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
  const [searchQuery, setSearchQuery] = useState("");

  const firstName = user?.full_name.split(" ")[0] ?? "";

  const sortedModules = modulesQuery.data
    ? [...modulesQuery.data].sort((a, b) => {
        const aComingSoon = a.status === "COMING_SOON" ? 1 : 0;
        const bComingSoon = b.status === "COMING_SOON" ? 1 : 0;
        return aComingSoon - bComingSoon || a.display_order - b.display_order;
      })
    : [];

  const activeModuleCount = modulesQuery.data?.filter((m) => m.status !== "COMING_SOON").length ?? 0;

  const navItems = [{ label: "DijiOne Home", href: "/", icon: Home, exact: true, external: false }];
  if (isPlatformAdmin) {
    navItems.push({ label: "Administration", href: "/admin", icon: ShieldCheck, exact: false, external: true });
  }

  return (
    <AppShell
      roleContext="platform"
      eyebrow="Dijital Team"
      title="DijiOne"
      topNavTitle="DijiOne Home"
      sections={[{ items: navItems }]}
      collapsible={{ storageKey: "dijione-sidebar-collapsed" }}
      topNavSearch={{ query: searchQuery, onSearch: setSearchQuery }}
      footer={
        <VersionFooter
          appName="DijiOne"
          version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
          gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
        />
      }
    >
      {/* Welcome area */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-dt-text-primary">
          {greeting()}, {firstName}.
        </h1>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
          <p className="text-sm text-dt-text-secondary">Here is what needs your attention today.</p>
          {modulesQuery.data && activeModuleCount > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs font-medium text-dt-burnt-orange">
              <span className="size-1.5 rounded-full bg-dt-orange" />
              {activeModuleCount} app{activeModuleCount !== 1 ? "s" : ""} available
            </span>
          )}
        </div>
      </div>

      {/* My Apps */}
      <section className="mb-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-dt-text-secondary">
          My Apps
        </h2>
        {/* Mobile-only search — TopNav handles desktop (sm+) via topNavSearch prop */}
        {modulesQuery.data && (
          <AppSearch
            modules={modulesQuery.data}
            query={searchQuery}
            onQueryChange={setSearchQuery}
            className="sm:hidden"
          />
        )}
        {modulesQuery.isLoading && <LoadingState label="Loading your apps…" />}
        {modulesQuery.isError && (
          <ErrorState message="Could not load DijiOne modules." onRetry={() => modulesQuery.refetch()} />
        )}
        {modulesQuery.data && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sortedModules
              .filter((m) => {
                const q = searchQuery.trim().toLowerCase();
                if (!q) return true;
                return m.name.toLowerCase().includes(q) || m.description.toLowerCase().includes(q);
              })
              .map((m) => (
                <ModuleCard key={m.key} module={m} />
              ))}
          </div>
        )}
      </section>

      {modulesQuery.data && <AttentionPanel modules={modulesQuery.data} />}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Activity */}
        <section className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-dt-text-secondary">
              Recent Activity
            </h2>
            {activityQuery.data && activityQuery.data.length > RECENT_ACTIVITY_LIMIT && (
              <Button variant="ghost" size="sm" onClick={() => setActivityExpanded((v) => !v)}>
                {activityExpanded ? "Show less" : "View all"}
              </Button>
            )}
          </div>
          <Card className="overflow-hidden p-0">
            {activityQuery.isLoading && <div className="p-4"><LoadingState label="Loading activity…" /></div>}
            {activityQuery.data && activityQuery.data.length === 0 && (
              <div className="p-4">
                <EmptyState title="No recent activity" description="Platform events will show up here." />
              </div>
            )}
            {activityQuery.data && activityQuery.data.length > 0 && (
              <ul className="divide-y divide-dt-border">
                {activityQuery.data
                  .slice(0, activityExpanded ? RECENT_ACTIVITY_EXPANDED_LIMIT : RECENT_ACTIVITY_LIMIT)
                  .map((n) => (
                    <li key={n.id} className="flex items-start gap-3 px-4 py-3.5 transition hover:bg-dt-surface-warm/60">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-dt-orange" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-dt-text-primary">{n.title}</p>
                          {n.related_entity_type && (
                            <span className="rounded-full bg-dt-cream px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-dt-burnt-orange">
                              {n.related_entity_type.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        {n.body && <p className="mt-0.5 text-sm text-dt-text-secondary">{n.body}</p>}
                        <p className="mt-1 text-xs text-dt-text-secondary/60">{formatDateTime(n.created_at)}</p>
                      </div>
                    </li>
                  ))}
              </ul>
            )}
          </Card>
        </section>

        {/* Right column */}
        <section className="flex flex-col gap-6">
          {/* Platform Health */}
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-dt-text-secondary">
              Platform Health
            </h2>
            {modulesQuery.data && <PlatformHealth modules={modulesQuery.data} />}
          </div>

          {/* Ask DijiOne */}
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-dt-text-secondary">
              Ask DijiOne
            </h2>
            <Card className="relative overflow-hidden border-dt-orange/20 bg-linear-to-br from-dt-red-deep to-dt-burnt-orange p-5 text-white shadow-sm">
              <div className="absolute -right-4 -top-4 size-24 rounded-full bg-white/5" />
              <div className="absolute -bottom-6 -right-6 size-32 rounded-full bg-white/5" />
              <div className="relative flex items-start gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/15">
                  <Sparkles className="size-4" />
                </div>
                <div>
                  <p className="text-sm font-semibold">Coming soon</p>
                  <p className="mt-1 text-xs leading-relaxed text-white/80">
                    Ask questions across your modules once Microsoft Copilot integration is live.
                  </p>
                </div>
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
