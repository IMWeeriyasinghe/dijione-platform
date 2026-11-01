import type { ReviewFlag } from "@/lib/dashboard";
import { FLAG_LABEL } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import type { IdentityClass } from "@/lib/types";
import { ToneBadge } from "./ToneBadge";

export function FlagChips({ flags }: { flags: ReviewFlag[] }) {
  if (!flags.length) return <span className="text-xs text-dt-text-secondary">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <ToneBadge key={f} tone="warning">
          {FLAG_LABEL[f]}
        </ToneBadge>
      ))}
    </span>
  );
}

export function IdentityBadge({ cls }: { cls: IdentityClass | null }) {
  if (!cls) return <ToneBadge tone="neutral">Details unavailable</ToneBadge>;
  const tone = cls === "MATCHED_ACTIVE" ? "success" : cls === "UNMATCHED" || cls === "AMBIGUOUS" ? "danger" : "warning";
  return <ToneBadge tone={tone}>{IDENTITY_LABEL[cls]}</ToneBadge>;
}

export function EmployeeCell({ name, code }: { name: string | null | undefined; code: string }) {
  return (
    <span className="flex flex-col">
      <span className="font-medium text-dt-text-primary">{name ?? "Unmatched code"}</span>
      <span className="font-mono text-xs text-dt-text-secondary">{code}</span>
    </span>
  );
}
