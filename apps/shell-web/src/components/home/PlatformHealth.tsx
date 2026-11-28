"use client";

import type { ModuleOut } from "@dijione/contracts";
import { Card } from "@dijione/design-system";
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { deriveModuleHealth, HEALTH_DISPLAY } from "@/lib/module-status";
import { useRuntimeStatus } from "./ModuleCard";

function ModuleHealthRow({ module }: { module: ModuleOut }) {
  const query = useRuntimeStatus(module.key, true);
  const health = deriveModuleHealth({ isPending: query.isPending, isSuccess: query.isSuccess, error: query.error });
  const display = HEALTH_DISPLAY[health];
  const Icon = health === "HEALTHY" ? CheckCircle2 : health === "UNAVAILABLE" ? XCircle : Clock;

  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <span className="truncate text-sm font-medium text-dt-text-primary">{module.name}</span>
      <span className={`flex shrink-0 items-center gap-1.5 text-xs ${display.text}`} title={display.title}>
        <Icon className="size-3.5" /> {display.label}
      </span>
    </li>
  );
}

/** Compact platform-wide rollup. Coming Soon modules are excluded — they have
 * no running service to report health for. Each row reuses the same isolated
 * per-module query ModuleCard already populates. */
export function PlatformHealth({ modules }: { modules: ModuleOut[] }) {
  const operationalModules = modules.filter((m) => m.status !== "COMING_SOON");
  if (operationalModules.length === 0) return null;

  return (
    <Card className="p-4">
      <ul className="divide-y divide-dt-border">
        {operationalModules.map((m) => (
          <ModuleHealthRow key={m.key} module={m} />
        ))}
      </ul>
    </Card>
  );
}
