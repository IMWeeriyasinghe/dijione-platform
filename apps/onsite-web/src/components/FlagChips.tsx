import type { ReviewFlag } from "@/lib/dashboard";
import { DATA_QUALITY_FLAGS, FLAG_HELP, FLAG_LABEL } from "@/lib/flags";
import { IDENTITY_LABEL, MAPPING_LABEL } from "@/lib/format";
import type { IdentityClass, MappingStatus } from "@/lib/types";
import { Person } from "./kit";
import { ToneBadge } from "./ToneBadge";

/** Review flags: amber for activity-pattern prompts, neutral for data-quality
 *  prompts. The explanation is available on hover and to screen readers. */
export function FlagChips({ flags, empty = "—" }: { flags: ReviewFlag[]; empty?: string }) {
  if (!flags.length) return <span className="text-xs text-dt-text-secondary">{empty}</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <span key={f} title={FLAG_HELP[f]}>
          <ToneBadge tone={DATA_QUALITY_FLAGS.has(f) ? "neutral" : "warning"}>
            {FLAG_LABEL[f]}
            <span className="sr-only">: {FLAG_HELP[f]}</span>
          </ToneBadge>
        </span>
      ))}
    </span>
  );
}

export function IdentityBadge({ cls }: { cls: IdentityClass | null }) {
  if (!cls) return <ToneBadge tone="neutral">Details unavailable</ToneBadge>;
  const tone = cls === "MATCHED_ACTIVE" ? "success" : cls === "UNMATCHED" || cls === "AMBIGUOUS" ? "danger" : "warning";
  return <ToneBadge tone={tone}>{IDENTITY_LABEL[cls]}</ToneBadge>;
}

/** Mapping Status: whether attendance is attributed through a verified
 *  ZKBioTime ID mapping, refined by the team member's record (legacy class). */
export function MappingBadge({ status, cls }: { status?: MappingStatus | null; cls?: IdentityClass | null }) {
  if (status === "MAPPED" || (!status && cls)) {
    if (cls && cls !== "MATCHED_ACTIVE") return <IdentityBadge cls={cls} />;
    return <ToneBadge tone="success">{MAPPING_LABEL.MAPPED}</ToneBadge>;
  }
  if (!status) return <ToneBadge tone="neutral">Details unavailable</ToneBadge>;
  const tone = status === "UNMAPPED" || status === "MAPPING_CONFLICT" ? "danger"
    : status === "DIRECTORY_UNAVAILABLE" ? "neutral" : "warning";
  return <ToneBadge tone={tone}>{MAPPING_LABEL[status]}</ToneBadge>;
}

export function EmployeeCell({ name, code, meta }: { name: string | null | undefined; code: string; meta?: React.ReactNode }) {
  return <Person name={name} code={code} meta={meta} />;
}
