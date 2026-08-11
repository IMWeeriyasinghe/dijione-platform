"use client";

import { useQuery } from "@tanstack/react-query";
import { Home, Sparkles } from "lucide-react";
import { listModules, listNotifications } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { AppShell } from "@/components/shell/AppShell";
import { AuthGate } from "@/components/shell/AuthGate";
import { Card } from "@/components/ui/Card";
import { ModuleCard } from "@/components/home/ModuleCard";
import { EmptyState, LoadingState, ErrorState } from "@/components/ui/States";
import { formatDateTime } from "@/lib/utils";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function HomeContent() {
  const { user } = useAuth();
  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: listModules });
  const activityQuery = useQuery({ queryKey: ["notifications"], queryFn: () => listNotifications() });

  const firstName = user?.full_name.split(" ")[0] ?? "";

  return (
    <AppShell
      eyebrow="Dijital Team"
      title="DijiOne"
      topNavTitle="DijiOne Home"
      sections={[{ items: [{ label: "DijiOne Home", href: "/", icon: Home, exact: true }] }]}
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
            {modulesQuery.data.map((m) => (
              <ModuleCard key={m.key} module={m} />
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
            Recent Activity
          </h2>
          <Card className="p-2">
            {activityQuery.isLoading && <LoadingState label="Loading activity…" />}
            {activityQuery.data && activityQuery.data.length === 0 && (
              <EmptyState title="No recent activity" description="Platform events will show up here." />
            )}
            {activityQuery.data && activityQuery.data.length > 0 && (
              <ul className="divide-y divide-dt-border">
                {activityQuery.data.slice(0, 8).map((n) => (
                  <li key={n.id} className="flex items-start gap-3 px-3 py-3">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-dt-orange" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-dt-text-primary">{n.title}</p>
                      {n.body && <p className="text-sm text-dt-text-secondary">{n.body}</p>}
                      <p className="mt-0.5 text-xs text-dt-text-secondary/70">{formatDateTime(n.created_at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
            Ask DijiOne
          </h2>
          <Card className="flex h-full flex-col items-start gap-3 bg-linear-to-br from-dt-red-deep to-dt-burnt-orange p-5 text-white">
            <div className="flex size-9 items-center justify-center rounded-xl bg-white/15">
              <Sparkles className="size-4.5" />
            </div>
            <p className="text-sm font-semibold">Copilot orchestration is coming to DijiOne.</p>
            <p className="text-sm text-white/85">
              Ask natural-language questions across your modules and trigger approved workflows —
              reserved for a future release once Microsoft Copilot / Cowork is wired in.
            </p>
          </Card>
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
