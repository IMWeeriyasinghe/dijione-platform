import { AlertTriangle, Check, Info, MoveRight, X } from "lucide-react";
import { StatusBadge } from "@dijione/design-system";
import {
  getInternalOrderStatusLabel,
  getOrderEventTone,
  getOrderEventTypeLabel,
  type OrderEventOut,
  type OrderEventTone,
} from "@dijione/contracts";

// Phase 1.6 (post-hardening review round) — the Raw Event Log keeps every
// field it already had (event, transition, detail, timestamp, actor); this
// only changes the rendering from a flat bordered list into a vertical
// activity timeline. Colour is never the only signal: each tone also gets
// its own icon (accessibility §7), and body text stays neutral — only the
// dot, its ring and a thin left accent carry colour.
const TONE_STYLES: Record<OrderEventTone, { icon: typeof Check; dot: string; accent: string }> = {
  success: {
    icon: Check,
    dot: "border-dt-success bg-[color-mix(in_srgb,var(--dt-success)_16%,white)] text-dt-success",
    accent: "border-dt-success",
  },
  warning: {
    icon: AlertTriangle,
    dot: "border-dt-warning bg-[color-mix(in_srgb,var(--dt-warning)_16%,white)] text-dt-warning",
    accent: "border-dt-warning",
  },
  progress: {
    icon: MoveRight,
    dot: "border-dt-burnt-orange bg-[color-mix(in_srgb,var(--dt-orange)_16%,white)] text-dt-burnt-orange",
    accent: "border-dt-burnt-orange",
  },
  error: {
    icon: X,
    dot: "border-dt-danger bg-[color-mix(in_srgb,var(--dt-danger)_14%,white)] text-dt-danger",
    accent: "border-dt-danger",
  },
  info: {
    icon: Info,
    dot: "border-dt-border bg-dt-surface-warm text-dt-text-secondary",
    accent: "border-dt-border",
  },
};

export function EventLogTimeline({ events }: { events: OrderEventOut[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-dt-text-secondary">No events recorded.</p>;
  }

  return (
    <ol className="flex flex-col gap-1" aria-label="Order event history, chronological">
      {events.map((event, index) => {
        const tone = getOrderEventTone(event);
        const { icon: Icon, dot, accent } = TONE_STYLES[tone];
        const isLast = index === events.length - 1;

        return (
          <li key={event.id} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast && (
              <span
                aria-hidden="true"
                className="absolute top-6 left-[11px] h-[calc(100%-1.5rem)] w-px bg-dt-border"
              />
            )}
            <span
              aria-hidden="true"
              className={`relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border-2 ${dot}`}
            >
              <Icon className="size-3.5" strokeWidth={2.5} />
            </span>
            <div className={`min-w-0 flex-1 border-l-2 pb-0.5 pl-3 ${accent}`}>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-dt-text-primary">
                  {getOrderEventTypeLabel(event.event_type)}
                </p>
                {event.to_status && (
                  <StatusBadge status={event.to_status} label={getInternalOrderStatusLabel(event.to_status)} />
                )}
              </div>
              {event.from_status && event.to_status && (
                <p className="mt-0.5 text-xs text-dt-text-secondary">
                  {getInternalOrderStatusLabel(event.from_status)} → {getInternalOrderStatusLabel(event.to_status)}
                </p>
              )}
              {event.detail && <p className="mt-1 text-sm text-dt-text-secondary">{event.detail}</p>}
              <p className="mt-1.5 text-xs text-dt-text-secondary">
                {event.actor_display_name ?? event.actor_type} ·{" "}
                {new Date(event.created_at).toLocaleString()}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
