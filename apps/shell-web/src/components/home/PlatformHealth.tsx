"use client";

import type { ModuleOut } from "@dijione/contracts";
import { Card } from "@dijione/design-system";
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { hasSummaryEndpoint, useRuntimeStatus } from "./ModuleCard";

function ModuleHealthRow({ module }: { module: ModuleOut }) {
  const comingSoon = module.status === "COMING_SOON";
  const enabled = !comingSoon && hasSummaryEndpoint(module.key);
  // Reuses the same isolated per-module query ModuleCard already populates
  // (identical queryKey) — React Query dedupes it, so this never issues a
  // second, coupled request; a dead module still only degrades its own row.
  const query = useRuntimeStatus(module.key, enabled);

  let icon = Clock;
  let tone = "text-dt-text-secondary";
  let label = "Coming soon";

  if (enabled) {
    if (query.isLoading) {
      icon = Clock;
      tone = "text-dt-text-secondary";
      label = "Checking…";
    } else if (query.isError) {
      icon = XCircle;
      tone = "text-dt-danger";
      label = "Degraded";
    } else {
      icon = CheckCircle2;
      tone = "text-dt-success";
      label = "Healthy";
    }
  } else if (!comingSoon) {
    // Active module with no summary endpoint wired up — nothing to report.
    return null;
  }

  const Icon = icon;
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="truncate text-sm text-dt-text-primary">{module.name}</span>
      <span className={`flex items-center gap-1.5 text-xs font-medium ${tone}`}>
        <Icon className="size-3.5" /> {label}
      </span>
    </li>
  );
}

/** Compact platform-wide rollup — same isolated per-module fetches
 * ModuleCard already makes, just aggregated for a glance-able summary.
 * Never a Promise.all: each row resolves (or fails) independently. */
export function PlatformHealth({ modules }: { modules: ModuleOut[] }) {
  return (
    <Card className="p-4">
      <p className="mb-1 text-sm font-semibold text-dt-text-primary">Platform Health</p>
      <ul className="divide-y divide-dt-border">
        {modules.map((m) => (
          <ModuleHealthRow key={m.key} module={m} />
        ))}
      </ul>
    </Card>
  );
}
