import { Check } from "lucide-react";
import { cn } from "../utils";
import type { StageProgress } from "@dijione/contracts";

export function StageTimeline({ stages }: { stages: StageProgress[] }) {
  return (
    <ol className="flex flex-col gap-0">
      {stages.map((s, i) => (
        <li key={s.stage} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            <div
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-[10px] font-bold",
                s.state === "DONE" && "border-dt-success bg-dt-success text-white",
                s.state === "CURRENT" && "border-dt-orange bg-dt-orange text-white",
                s.state === "UPCOMING" && "border-dt-border bg-dt-surface text-dt-text-secondary"
              )}
            >
              {s.state === "DONE" ? <Check className="size-3.5" /> : i + 1}
            </div>
            {i < stages.length - 1 && (
              <div
                className={cn(
                  "w-0.5 flex-1 min-h-6",
                  s.state === "DONE" ? "bg-dt-success" : "bg-dt-border"
                )}
              />
            )}
          </div>
          <div className={cn("pb-6 pt-0.5 text-sm", s.state === "UPCOMING" && "text-dt-text-secondary")}>
            <span className={cn(s.state === "CURRENT" && "font-semibold text-dt-burnt-orange")}>
              {s.label}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function CompactStageStrip({ stages }: { stages: StageProgress[] }) {
  return (
    <div className="flex items-center gap-1">
      {stages.map((s) => (
        <div
          key={s.stage}
          title={s.label}
          className={cn(
            "h-1.5 flex-1 rounded-full",
            s.state === "DONE" && "bg-dt-success",
            s.state === "CURRENT" && "bg-dt-orange",
            s.state === "UPCOMING" && "bg-dt-border"
          )}
        />
      ))}
    </div>
  );
}

export function StageProgressBar({ percent }: { percent: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-dt-surface-warm">
        <div
          className="h-full rounded-full bg-linear-to-r from-dt-red to-dt-orange transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-dt-burnt-orange">{percent}%</span>
    </div>
  );
}
