import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { Card } from "./Card";
import { cn } from "../utils";

export function MetricCard({
  label,
  value,
  icon: Icon,
  tone = "neutral",
  href,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone?: "neutral" | "brand";
  // Optional click-through destination (dashboard widget -> filtered list).
  // Purely a display convenience — the destination route enforces its own
  // server-side authorization/scope; this never substitutes for it.
  href?: string;
}) {
  const body = (
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
  );

  if (href) {
    return (
      <Link href={href} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-2 rounded-2xl">
        <Card className="p-5 transition-shadow hover:shadow-[0_4px_12px_rgba(36,20,15,0.08)] hover:border-dt-orange/30">
          {body}
        </Card>
      </Link>
    );
  }

  return <Card className="p-5">{body}</Card>;
}
