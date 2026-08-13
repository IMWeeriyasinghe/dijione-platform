import { cn, stageLabel } from "../utils";

type Tone = "success" | "warning" | "danger" | "neutral" | "brand";

const STATUS_TONE: Record<string, Tone> = {
  // Lifecycle / Customer Success status
  PENDING_REVIEW: "warning",
  CLARIFICATION_REQUIRED: "warning",
  APPROVED: "success",
  IN_PROGRESS: "brand",
  ON_HOLD: "warning",
  FULFILLED: "success",
  CANCELLED: "danger",
  REJECTED: "danger",
  // TA status
  NOT_STARTED: "neutral",
  VALIDATING: "brand",
  ATS_LINKED: "brand",
  COMPLETED: "success",
  // Application status
  ACTIVE: "brand",
  SHORTLISTED: "brand",
  CLIENT_REVIEW: "brand",
  OFFER: "warning",
  HIRED: "success",
  WITHDRAWN: "neutral",
  // Interview status
  SCHEDULED: "brand",
  RESCHEDULED: "warning",
  NO_SHOW: "danger",
  // Sync status
  SYNCED: "success",
  ERROR: "danger",
  PENDING: "warning",
  // Misc
  ACTIVE_CLIENT: "success",
  COMING_SOON: "neutral",
};

const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-[color-mix(in_srgb,var(--dt-success)_14%,white)] text-dt-success border-dt-success/20",
  warning: "bg-[color-mix(in_srgb,var(--dt-warning)_14%,white)] text-dt-warning border-dt-warning/20",
  danger: "bg-[color-mix(in_srgb,var(--dt-danger)_12%,white)] text-dt-danger border-dt-danger/20",
  neutral: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
  brand: "bg-[color-mix(in_srgb,var(--dt-orange)_14%,white)] text-dt-burnt-orange border-dt-orange/25",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        TONE_CLASSES[tone]
      )}
    >
      {label ?? stageLabel(status)}
    </span>
  );
}
