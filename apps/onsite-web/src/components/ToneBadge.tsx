const TONE_CLASSES = {
  success: "bg-dt-success/10 text-dt-success border-dt-success/30",
  warning: "bg-dt-amber/10 text-dt-burnt-orange border-dt-amber/40",
  danger: "bg-dt-danger/10 text-dt-danger border-dt-danger/30",
  neutral: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
} as const;

export type Tone = keyof typeof TONE_CLASSES;

export function ToneBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
