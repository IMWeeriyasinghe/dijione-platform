"use client";

import type { ModuleOut } from "@dijione/contracts";
import { Card } from "@dijione/design-system";
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { deriveModuleHealth, HEALTH_DISPLAY } from "@/lib/module-status";
import { useRuntimeStatus } from "./ModuleCard";

function ModuleHealthRow({ module }: { module: ModuleOut }) {
  const comingSoon = module.status === "COMING_SOON";
  const enabled = !comingSoon;
  // Reuses the same isolated per-module query ModuleCard already populates
  // (identical queryKey) — React Query dedupes it, so this never issues a
  // second, coupled request; a dead module still only degrades its own row.
  const query = useRuntimeStatus(module.key, enabled);

  const health = deriveModuleHealth({ isPending: query.isPending, isSuccess: query.isSuccess, error: query.error });
  const display = enabled ? HEALTH_DISPLAY[health] : null;
  const icon = !display ? Clock : health === "HEALTHY" ? CheckCircle2 : health === "UNAVAILABLE" ? XCircle : Clock;
  const tone = display?.text ?? "font-medium text-dt-text-secondary";
  const label = display?.label ?? "Coming soon";

  const Icon = icon;
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <span className="truncate text-sm text-dt-text-primary">{module.name}</span>
      <span className={`flex items-center gap-1.5 text-xs ${tone}`} title={display?.title}>
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
