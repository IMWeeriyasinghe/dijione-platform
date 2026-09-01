import { cn, stageLabel } from "../utils";

type Tone = "success" | "warning" | "danger" | "neutral" | "brand";

const STATUS_TONE: Record<string, Tone> = {
  // Canonical recruitment stages (CanonicalStage) not already covered below
  // by an overlapping Lifecycle/Application-status key — a promoted, real
  // Lever-sourced TalentRequest/Application legitimately carries these far
  // more often than the old mock data did, so an unmapped grey badge here
  // is a much more visible gap with real data.
  REQUEST_SUBMITTED: "neutral",
  REQUIREMENT_CONFIRMED: "brand",
  SOURCING: "brand",
  SCREENING: "brand",
  INTERVIEWS: "brand",
  ONBOARDING: "brand",
  DEPLOYED: "success",
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
  // Magic-link external client access grant (MagicLinkGrant.status) —
  // ACTIVE reuses the existing "brand" mapping.
  EXPIRED: "neutral",
  REVOKED: "danger",
  // Access source / group status
  DIRECT: "brand",
  GROUP: "success",
  SYSTEM: "neutral",
  INACTIVE: "neutral",
  // DijiBirthday order status (semi-automation future-state plan §P) —
  // previously almost entirely unmapped, so every birthday order rendered
  // grey regardless of state.
  PENDING_VERIFICATION: "warning",
  REQUIRES_REVIEW: "warning",
  REQUIRES_ATTENTION: "danger",
  SENT_TO_SUPPLIER: "brand",
  CHANGE_REQUESTED: "warning",
  CONFIRMED: "brand",
  PREPARING: "brand",
  OUT_FOR_DELIVERY: "brand",
  DELIVERED: "success",
  UNABLE_TO_FULFIL: "danger",
  // DijiBirthday address-verification status
  NOT_CHECKED: "neutral",
  VERIFICATION_REQUESTED: "warning",
  VERIFIED: "success",
  NEEDS_UPDATE: "danger",
  NOT_APPLICABLE: "neutral",
  // DijiBirthday lead-time class
  NORMAL: "success",
  SHORT_NOTICE: "warning",
  URGENT: "danger",
  // DijiBirthday eligibility groups (Upcoming Birthdays)
  ELIGIBLE: "success",
  NEEDS_ATTENTION: "danger",
  FUTURE_STARTER: "neutral",
  NOT_ELIGIBLE: "neutral",
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
