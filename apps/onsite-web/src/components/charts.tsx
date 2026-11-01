"use client";

// Lightweight SVG charts on the DijiOne brand tokens — no chart dependency.
// Each chart has an accessible summary (role="img" + aria-label) and every
// bar carries a native tooltip (<title>) with its exact value.

import type { ReviewFlag } from "@/lib/dashboard";
import { FLAG_LABEL } from "@/lib/flags";

const H = 160;

function niceMax(values: number[]): number {
  const max = Math.max(1, ...values);
  const mag = 10 ** Math.floor(Math.log10(max));
  return Math.ceil(max / mag) * mag;
}

export function ColumnChart({ data, label, valueLabel, xLabel, highlightLast = false }: {
  data: { key: string; value: number; tick?: string }[];
  label: string;
  valueLabel: string;
  xLabel?: (key: string) => string;
  highlightLast?: boolean;
}) {
  const max = niceMax(data.map((d) => d.value));
  const total = data.reduce((s, d) => s + d.value, 0);
  const n = Math.max(1, data.length);
  const slot = 100 / n;
  return (
    <figure>
      <svg
        role="img"
        aria-label={`${label}: ${total.toLocaleString()} ${valueLabel} in total`}
        viewBox={`0 0 100 ${H}`}
        preserveAspectRatio="none"
        className="h-44 w-full"
      >
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1="0" x2="100" y1={H - f * (H - 8)} y2={H - f * (H - 8)} stroke="var(--dt-border)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
        ))}
        {data.map((d, i) => {
          const h = (d.value / max) * (H - 8);
          const last = highlightLast && i === data.length - 1;
          return (
            <rect
              key={d.key}
              x={i * slot + slot * 0.15}
              y={H - h}
              width={slot * 0.7}
              height={Math.max(h, d.value ? 1 : 0)}
              rx="0.6"
              fill={last ? "var(--dt-red)" : "var(--dt-orange)"}
              opacity={d.value ? 1 : 0.25}
            >
              <title>{`${xLabel ? xLabel(d.key) : d.key}: ${d.value.toLocaleString()} ${valueLabel}`}</title>
            </rect>
          );
        })}
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-dt-text-secondary">
        {data.map((d, i) => (
          <span key={d.key} className="min-w-0 flex-1 truncate text-center" aria-hidden="true">
            {d.tick !== undefined ? d.tick : i % Math.ceil(n / 8) === 0 ? (xLabel ? xLabel(d.key) : d.key) : ""}
          </span>
        ))}
      </div>
      <figcaption className="sr-only">{label}</figcaption>
    </figure>
  );
}

export function BreakdownBars({ counts }: { counts: Record<ReviewFlag, number> }) {
  const entries = (Object.keys(FLAG_LABEL) as ReviewFlag[]).map((f) => [f, counts[f] ?? 0] as const);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <ul className="space-y-2" aria-label="Review breakdown">
      {entries.map(([flag, value]) => (
        <li key={flag} className="grid grid-cols-[minmax(9rem,12rem)_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="truncate text-dt-text-secondary">{FLAG_LABEL[flag]}</span>
          <span className="h-2.5 overflow-hidden rounded-full bg-dt-surface-warm">
            <span
              className="block h-full rounded-full bg-gradient-to-r from-dt-red to-dt-orange"
              style={{ width: `${(value / max) * 100}%` }}
            />
          </span>
          <span className="text-right font-medium tabular-nums text-dt-text-primary">{value}</span>
        </li>
      ))}
    </ul>
  );
}
