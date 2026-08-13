import type { LucideIcon } from "lucide-react";
import { Card } from "./Card";
import { cn } from "../utils";

export function MetricCard({
  label,
  value,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: "neutral" | "brand";
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-dt-text-secondary">{label}</p>
          <p className="mt-1.5 text-2xl font-semibold text-dt-text-primary">{value}</p>
        </div>
        <div
          className={cn(
            "flex size-9 items-center justify-center rounded-xl",
            tone === "brand"
              ? "bg-linear-to-br from-dt-red to-dt-orange text-white"
              : "bg-dt-surface-warm text-dt-burnt-orange"
          )}
        >
          <Icon className="size-4.5" />
        </div>
      </div>
    </Card>
  );
}
