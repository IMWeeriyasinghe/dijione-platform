import type { MappingState, PunchSequence, ReviewFlag } from "@/lib/dashboard";
import { DATA_QUALITY_FLAGS, FLAG_HELP, FLAG_LABEL } from "@/lib/flags";
import { IDENTITY_LABEL, MAPPING_LABEL, MAPPING_STATE, SEQUENCE_LABEL } from "@/lib/format";
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
    return <ToneBadge tone={MAPPING_STATE.VERIFIED.tone}>{MAPPING_LABEL.MAPPED}</ToneBadge>;
  }
  if (!status) return <ToneBadge tone="neutral">Details unavailable</ToneBadge>;
  const tone = status === "MAPPING_CONFLICT" ? MAPPING_STATE.CONFLICT.tone
    : status === "UNMAPPED" ? MAPPING_STATE.UNMAPPED.tone
    : status === "DIRECTORY_UNAVAILABLE" ? "neutral" : "warning";
  return <ToneBadge tone={tone}>{MAPPING_LABEL[status]}</ToneBadge>;
}

/** Identity state of one recorded event for its own day (shared colours, see
 *  MAPPING_STATE). Verified events keep the employment refinement badge. */
export function MappingStateBadge({ state, status, cls }: {
  state?: MappingState; status?: MappingStatus | null; cls?: IdentityClass | null;
}) {
  if (!state || state === "VERIFIED") return <MappingBadge status={status} cls={cls} />;
  const s = MAPPING_STATE[state];
  return (
    <span title={s.help}>
      <ToneBadge tone={s.tone}>{s.label}<span className="sr-only">: {s.help}</span></ToneBadge>
    </span>
  );
}

/** First / last / intermediate / single recorded punch of the identity's
 *  complete site-local day — a neutral marker, separate from identity colours,
 *  and never a check-in / check-out. */
export function SequenceMarker({ seq, position, total }: { seq?: PunchSequence; position?: number; total?: number }) {
  if (!seq) return <span className="text-xs text-dt-text-secondary">—</span>;
  const glyph = { FIRST: "▶", LAST: "◀", INTERMEDIATE: "·", SINGLE: "◆" }[seq];
  const of = position && total ? ` (${position} of ${total})` : "";
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-dt-text-secondary"
      title={`${SEQUENCE_LABEL[seq]} of the whole site-local day${of}. Recorded order only. The last fingerprint is not an exit.`}>
      <span aria-hidden className="font-mono text-dt-text-primary">{glyph}</span>
      {SEQUENCE_LABEL[seq]}{of && <span className="tabular-nums">{of}</span>}
    </span>
  );
}

export function EmployeeCell({ name, code, meta }: { name: string | null | undefined; code: string; meta?: React.ReactNode }) {
  return <Person name={name} code={code} meta={meta} />;
}
