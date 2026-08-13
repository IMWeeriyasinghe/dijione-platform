"use client";

import { MODULE_TALENT_FLOW, type ModuleOut } from "@dijione/contracts";
import { useTalentScope } from "@dijione/auth-client";
import { Card } from "@dijione/design-system";
import { AlertCircle, CalendarClock } from "lucide-react";
import { useRuntimeStatus } from "./ModuleCard";

type AttentionItem = {
  key: string;
  icon: typeof AlertCircle;
  text: string;
};

/** Role-aware "needs your attention" strip. Every item here is derived from
 * a real field already present in a module's `/summary` payload — nothing
 * is invented. Aggregate counts (e.g. pending_requests) are cross-tenant,
 * so they're only ever shown to DijiTalentFlow staff roles (TA/Customer
 * Success), never to a TALENT_CLIENT user, to avoid leaking other clients'
 * volumes across the tenant boundary. If a module has no backing data for
 * a given item, that item is simply omitted. */
export function AttentionPanel({ modules }: { modules: ModuleOut[] }) {
  const talentScope = useTalentScope();
  const talentModule = modules.find((m) => m.key === MODULE_TALENT_FLOW && m.status !== "COMING_SOON");
  const talentSummary = useRuntimeStatus(MODULE_TALENT_FLOW, Boolean(talentModule));

  const items: AttentionItem[] = [];

  if (talentModule && talentScope?.isStaff && talentSummary.data) {
    const { pending_requests, interviews_upcoming } = talentSummary.data;
    if (typeof pending_requests === "number" && pending_requests > 0) {
      items.push({
        key: "talent-pending",
        icon: AlertCircle,
        text: `${pending_requests} DijiTalentFlow request${pending_requests === 1 ? "" : "s"} awaiting Customer Success review`,
      });
    }
    if (typeof interviews_upcoming === "number" && interviews_upcoming > 0) {
      items.push({
        key: "talent-interviews",
        icon: CalendarClock,
        text: `${interviews_upcoming} interview${interviews_upcoming === 1 ? "" : "s"} scheduled soon in DijiTalentFlow`,
      });
    }
  }

  if (items.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Needs Your Attention
      </h2>
      <Card className="p-2">
        <ul className="divide-y divide-dt-border">
          {items.map(({ key, icon: Icon, text }) => (
            <li key={key} className="flex items-center gap-3 px-3 py-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-dt-cream text-dt-burnt-orange">
                <Icon className="size-4" />
              </span>
              <p className="text-sm font-medium text-dt-text-primary">{text}</p>
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}
