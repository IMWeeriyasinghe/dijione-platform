"use client";

import type { ModuleOut } from "@dijione/contracts";
import { request } from "@dijione/auth-client";
import { Card, cn } from "@dijione/design-system";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { ModuleIcon } from "@/lib/module-icons";

// Maps a module registry key to its owning service's summary endpoint (CR
// §15). Modules with no entry here have no runtime status to show (e.g. a
// module.route the shell itself doesn't proxy anywhere).
const MODULE_SUMMARY_PATH: Record<string, string> = {
  "talent-flow": "/api/talent/summary",
  birthday: "/api/birthday/summary",
  spark: "/api/spark/summary",
};

/** Each card fetches its own service's health independently — never one
 * Promise.all for the whole page — so a single dead backend degrades one
 * card, not the DijiOne Home page (CR §39). A 4s timeout keeps a hung
 * service from blocking the UI indefinitely (CR §17). */
function useRuntimeStatus(moduleKey: string, enabled: boolean) {
  const summaryPath = MODULE_SUMMARY_PATH[moduleKey];
  return useQuery({
    queryKey: ["module-summary", moduleKey],
    queryFn: () => request<{ status: string }>(summaryPath, { signal: AbortSignal.timeout(4000) }),
    enabled: enabled && Boolean(summaryPath),
    retry: 0,
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

function RuntimeStatusBadge({ moduleKey, enabled }: { moduleKey: string; enabled: boolean }) {
  const query = useRuntimeStatus(moduleKey, enabled);
  if (!enabled || !MODULE_SUMMARY_PATH[moduleKey]) return null;

  if (query.isLoading) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-dt-text-secondary">
        <span className="size-1.5 rounded-full bg-dt-text-secondary/40" /> Checking…
      </span>
    );
  }
  if (query.isError) {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium text-dt-danger">
        <span className="size-1.5 rounded-full bg-dt-danger" /> Temporarily unavailable
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-dt-success">
      <span className="size-1.5 rounded-full bg-dt-success" /> Healthy
    </span>
  );
}

export function ModuleCard({ module }: { module: ModuleOut }) {
  const comingSoon = module.status === "COMING_SOON";

  const content = (
    <Card
      className={cn(
        "group relative flex h-full flex-col gap-4 overflow-hidden p-5 transition",
        comingSoon ? "opacity-70" : "hover:-translate-y-0.5 hover:shadow-md"
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex size-11 items-center justify-center rounded-2xl bg-linear-to-br from-dt-red to-dt-orange text-white">
          <ModuleIcon iconKey={module.icon} className="size-5" />
        </div>
        {comingSoon && (
          <span className="rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs font-medium text-dt-text-secondary">
            Coming soon
          </span>
        )}
      </div>
      <div>
        <p className="text-base font-semibold text-dt-text-primary">{module.name}</p>
        <p className="mt-1 text-sm text-dt-text-secondary">{module.description}</p>
      </div>
      <RuntimeStatusBadge moduleKey={module.key} enabled={!comingSoon} />
      {!comingSoon && (
        <div className="mt-auto flex items-center gap-1 text-sm font-medium text-dt-burnt-orange">
          Open
          <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
        </div>
      )}
    </Card>
  );

  if (comingSoon) return <div>{content}</div>;
  // Plain <a>, not next/link: every module route is a different Next.js
  // zone (proxied to its own app), so this must be a full navigation —
  // next/link would soft-navigate and silently strand the user on Home
  // with just the URL bar updated (see Sidebar's NavItem.external).
  return <a href={module.route}>{content}</a>;
}
