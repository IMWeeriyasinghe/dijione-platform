import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ModuleOut } from "@/lib/types";
import { ModuleIcon } from "@/lib/module-icons";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

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
      {!comingSoon && (
        <div className="mt-auto flex items-center gap-1 text-sm font-medium text-dt-burnt-orange">
          Open
          <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
        </div>
      )}
    </Card>
  );

  if (comingSoon) return <div>{content}</div>;
  return <Link href={module.route}>{content}</Link>;
}
