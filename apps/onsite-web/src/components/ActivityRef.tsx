"use client";

import { Fingerprint } from "lucide-react";
import type { ActivityEvent } from "@/lib/dashboard";
import { EmployeeRefCell } from "./kit";

export const isVerifiedEvent = (e: ActivityEvent) => !e.mapping_state || e.mapping_state === "VERIFIED";

/** Raw ZKBioTime ID of an unverified event — never a name, photo or hint. */
export function UnverifiedRef({ e }: { e: ActivityEvent }) {
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-dt-amber/15 text-dt-warning">
        <Fingerprint className="size-4" />
      </span>
      <span className="min-w-0">
        <span className="block whitespace-nowrap font-medium text-dt-text-primary">
          ZKBioTime ID <span className="font-mono">{e.emp_code}</span>
        </span>
        <span className="block text-xs text-dt-text-secondary">
          {e.mapping_state === "CONFLICT" ? "Mapping conflict, not attributed" : "Not mapped to a team member"}
        </span>
      </span>
    </span>
  );
}

/** Who recorded an event: the verified team member, or the raw ZKBioTime ID. */
export function ActivityWho({ e }: { e: ActivityEvent }) {
  return isVerifiedEvent(e) ? <EmployeeRefCell r={e} meta={e.department ?? undefined} size="sm" /> : <UnverifiedRef e={e} />;
}
