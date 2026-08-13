"use client";

import type { ModuleOut } from "@dijione/contracts";
import { request, useAuth } from "@dijione/auth-client";
import { Card, cn, stageLabel } from "@dijione/design-system";
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

/** Shape returned by each module's `/summary` route. `status` is the only
 * field every service is guaranteed to send back — everything else is
 * service-specific and optional, so callers must not assume it exists. */
export type ModuleSummary = {
  status: string;
  service?: string;
  open_requests?: number;
  pending_requests?: number;
  interviews_upcoming?: number;
};

/** Each card fetches its own service's health independently — never one
 * Promise.all for the whole page — so a single dead backend degrades one
 * card, not the DijiOne Home page (CR §39). A 4s timeout keeps a hung
 * service from blocking the UI indefinitely (CR §17).
 *
 * Exported so other Home widgets (AttentionPanel, PlatformHealth) can read
 * the same already-resolved React Query cache entry instead of issuing a
 * second, coupled fetch — React Query dedupes identical queryKeys, so this
 * still fires one isolated request per module, never a joint one. */
export function useRuntimeStatus(moduleKey: string, enabled: boolean) {
  const summaryPath = MODULE_SUMMARY_PATH[moduleKey];
  return useQuery({
    queryKey: ["module-summary", moduleKey],
    queryFn: () => request<ModuleSummary>(summaryPath, { signal: AbortSignal.timeout(4000) }),
    enabled: enabled && Boolean(summaryPath),
    retry: 0,
    staleTime: 15_000,
    refetchInterval: 60_000,
  });
}

export function hasSummaryEndpoint(moduleKey: string): boolean {
  return Boolean(MODULE_SUMMARY_PATH[moduleKey]);
}

// Human-readable labels for the operational fields a summary payload may
// carry. Only fields present in the real payload are ever rendered — see
// apps/talent-api/app/api/routes/talent_summary.py for what talent-flow
// actually returns; birthday/spark have no summary route yet (COMING_SOON,
// never fetched) so they render no stats.
const SUMMARY_FIELD_LABELS: Record<string, string> = {
  open_requests: "Open requests",
  pending_requests: "Pending review",
  interviews_upcoming: "Interviews upcoming",
};

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

  const stats = Object.entries(SUMMARY_FIELD_LABELS).filter(
    ([field]) => typeof query.data?.[field as keyof ModuleSummary] === "number"
  );

  return (
    <div className="flex flex-col gap-2">
      <span className="flex items-center gap-1.5 text-xs font-medium text-dt-success">
        <span className="size-1.5 rounded-full bg-dt-success" /> Healthy
      </span>
      {stats.length > 0 && (
        <dl className="flex flex-wrap gap-x-4 gap-y-1">
          {stats.map(([field, label]) => (
            <div key={field} className="flex items-baseline gap-1">
              <dt className="text-xs text-dt-text-secondary">{label}</dt>
              <dd className="text-xs font-semibold text-dt-text-primary">
                {query.data?.[field as keyof ModuleSummary] as number}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function ModuleCard({ module }: { module: ModuleOut }) {
  const { user } = useAuth();
  const comingSoon = module.status === "COMING_SOON";
  const roleForModule = user?.module_roles.find((r) => r.module_key === module.key);

  const content = (
    <Card
      className={cn(
        "group relative flex h-full flex-col gap-4 overflow-hidden transition",
        comingSoon ? "p-4 opacity-70" : "p-5 hover:-translate-y-0.5 hover:shadow-md"
      )}
    >
      <div className="flex items-center justify-between">
        <div
          className={cn(
            "flex items-center justify-center rounded-2xl bg-linear-to-br from-dt-red to-dt-orange text-white",
            comingSoon ? "size-9 opacity-80" : "size-11"
          )}
        >
          <ModuleIcon iconKey={module.icon} className={comingSoon ? "size-4" : "size-5"} />
        </div>
        {comingSoon && (
          <span className="rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-dt-text-secondary">
            Coming soon
          </span>
        )}
      </div>
      <div>
        <p className={cn("font-semibold text-dt-text-primary", comingSoon ? "text-sm" : "text-base")}>
          {module.name}
        </p>
        <p className="mt-1 text-sm text-dt-text-secondary">{module.description}</p>
      </div>
      {!comingSoon && roleForModule && (
        <span className="inline-flex w-fit items-center rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs font-medium text-dt-burnt-orange">
          Your role: {stageLabel(roleForModule.role)}
        </span>
      )}
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
