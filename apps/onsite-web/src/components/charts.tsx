"use client";

// Lightweight, dependency-free charts on the DijiOne brand tokens. Every chart
// names its measure, period and site; has a y-axis, readable x labels that
// thin out on small screens, hover AND keyboard-focus tooltips with the exact
// value, an accessible summary, and a real empty state. Bars can be made
// selectable for drill-down (`onSelect`).

import { useState } from "react";
import Link from "next/link";
import { BarChart3, ChevronRight } from "lucide-react";
import type { ReviewFlag } from "@/lib/dashboard";
import { DATA_QUALITY_FLAGS, FLAG_HELP, FLAG_LABEL } from "@/lib/flags";
import { fmtNum } from "@/lib/period";
import { cx, focusRing, InfoTip } from "./kit";

export type Bar = {
  key: string;
  value: number;
  /** Full label for the tooltip, e.g. "Mon 3 Nov" or "08:00–08:59". */
  label: string;
  /** Short axis label, e.g. "3 Nov" or "08". */
  tick: string;
  /** Optional second line in the tooltip. */
  note?: string;
};

function niceMax(max: number): number {
  if (max <= 4) return 4;
  const mag = 10 ** Math.floor(Math.log10(max));
  const n = max / mag;
  return (n <= 2 ? 2 : n <= 4 ? 4 : n <= 5 ? 5 : 10) * mag;
}

export function BarChart({ data, measure, summary, selected, onSelect, highlight, tickEvery = [1, 1], average, empty, height = 176 }: {
  data: Bar[];
  /** Plural unit, e.g. "events". */
  measure: string;
  /** Accessible description including period and site. */
  summary: string;
  selected?: string | null;
  onSelect?: (key: string) => void;
  /** Keys drawn in the accent colour (e.g. the peak hour). */
  highlight?: Set<string>;
  /** Show every Nth x label: [phones, sm and up]. */
  tickEvery?: [number, number];
  /** Optional reference line (e.g. daily average over active days). */
  average?: { value: number; label: string } | null;
  empty?: React.ReactNode;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0);
  const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
  const ticks = [max, max / 2, 0];

  if (total === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg bg-dt-surface-warm/50 px-4 text-center" style={{ height }}>
        <BarChart3 className="size-6 text-dt-text-secondary/60" aria-hidden />
        <div className="text-sm text-dt-text-secondary">{empty ?? `No ${measure} recorded in this period.`}</div>
      </div>
    );
  }

  const tip = hover !== null ? data[hover] : null;
  return (
    <figure className="min-w-0">
      <div className="flex gap-2">
        <div className="flex shrink-0 flex-col justify-between text-right text-[11px] tabular-nums text-dt-text-secondary" style={{ height }} aria-hidden>
          {ticks.map((t) => <span key={t} className="-translate-y-1/2 first:translate-y-0 last:translate-y-0">{fmtNum(Math.round(t))}</span>)}
        </div>
        <div className="relative min-w-0 flex-1" style={{ height }} onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <span key={t} aria-hidden className="absolute inset-x-0 border-t border-dashed border-dt-border/80" style={{ bottom: `${(t / max) * 100}%` }} />
          ))}
          {average && average.value > 0 && (
            <span aria-hidden className="absolute inset-x-0 z-[1] border-t-2 border-dt-info/60" style={{ bottom: `${(average.value / max) * 100}%` }}>
              <span className="absolute -top-4 right-0 rounded bg-dt-surface/90 px-1 text-[10px] text-dt-info">{average.label}</span>
            </span>
          )}
          <div role="list" aria-label={summary} className="absolute inset-0 flex items-end gap-[2px] sm:gap-1">
            {data.map((d, i) => {
              const h = (d.value / max) * 100;
              const isSel = selected === d.key;
              const accent = isSel || highlight?.has(d.key);
              const text = `${d.label}: ${fmtNum(d.value)} ${measure}${d.note ? ` · ${d.note}` : ""}`;
              const barCls = cx("block w-full rounded-t-sm transition-colors motion-reduce:transition-none",
                d.value === 0 ? "bg-dt-border/70" : accent ? "bg-dt-red" : "bg-dt-orange",
                hover === i && d.value > 0 && !accent && "bg-dt-orange/80");
              const common = {
                onMouseEnter: () => setHover(i), onFocus: () => setHover(i), onBlur: () => setHover(null),
                className: cx("relative flex h-full min-w-0 flex-1 items-end rounded-sm", focusRing, isSel && "bg-dt-red/5"),
              };
              return (
                <div role="listitem" key={d.key} className="flex h-full min-w-0 flex-1">
                  {onSelect ? (
                    <button type="button" aria-label={text} aria-pressed={isSel} onClick={() => onSelect(d.key)} {...common}>
                      <span className={barCls} style={{ height: `${Math.max(h, d.value ? 2 : 1)}%` }} />
                    </button>
                  ) : (
                    <span tabIndex={0} aria-label={text} {...common}>
                      <span className={barCls} style={{ height: `${Math.max(h, d.value ? 2 : 1)}%` }} />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          {tip && hover !== null && (
            <div role="tooltip" className="pointer-events-none absolute z-20 -translate-x-1/2 whitespace-nowrap rounded-lg border border-dt-border bg-dt-surface px-2.5 py-1.5 text-xs shadow-lg"
              style={{ left: `${Math.min(88, Math.max(12, ((hover + 0.5) / data.length) * 100))}%`, bottom: `calc(${Math.min(100, (tip.value / max) * 100)}% + 6px)` }}>
              <div className="font-medium text-dt-text-primary">{tip.label}</div>
              <div className="text-dt-text-secondary"><span className="font-semibold tabular-nums text-dt-text-primary">{fmtNum(tip.value)}</span> {measure}</div>
              {tip.note && <div className="text-dt-text-secondary">{tip.note}</div>}
              {onSelect && <div className="mt-0.5 text-[10px] text-dt-burnt-orange">Click to inspect</div>}
            </div>
          )}
        </div>
      </div>
      <div className="mt-1.5 flex gap-[2px] pl-8 text-[11px] text-dt-text-secondary sm:gap-1" aria-hidden>
        {data.map((d, i) => (
          <span key={d.key} className="min-w-0 flex-1 overflow-visible whitespace-nowrap text-center">
            <span className={cx(i % tickEvery[0] === 0 ? "inline" : "hidden", i % tickEvery[1] === 0 ? "sm:inline" : "sm:hidden",
              selected === d.key && "font-semibold text-dt-red")}>{d.tick}</span>
          </span>
        ))}
      </div>
      <figcaption className="sr-only">{summary}. Total {fmtNum(total)} {measure}.</figcaption>
    </figure>
  );
}

/** Review categories as drill-down rows. Counts are employee-days with the
 *  flag — prompts for review, never confirmed violations. */
export function BreakdownList({ counts, hrefFor, unit = "employee-days" }: {
  counts: Record<ReviewFlag, number>; hrefFor: (flag: ReviewFlag) => string; unit?: string;
}) {
  const entries = (Object.keys(FLAG_LABEL) as ReviewFlag[]).map((f) => [f, counts[f] ?? 0] as const)
    .sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <ul className="divide-y divide-dt-border/60" aria-label="Review categories">
      {entries.map(([flag, value]) => (
        <li key={flag} className="flex items-center gap-1">
          <Link href={hrefFor(flag)} aria-label={`${FLAG_LABEL[flag]}: ${value} ${unit}. Open in Exceptions`}
            className={cx("group grid min-h-11 flex-1 grid-cols-[minmax(0,1fr)_minmax(3rem,30%)_2.5rem_1rem] items-center gap-3 rounded-md px-1 text-sm hover:bg-dt-surface-warm/60", focusRing,
              value === 0 && "opacity-60")}>
            <span className="truncate text-dt-text-primary">{FLAG_LABEL[flag]}</span>
            <span className="h-2 overflow-hidden rounded-full bg-dt-surface-warm">
              <span className={cx("block h-full rounded-full", DATA_QUALITY_FLAGS.has(flag) ? "bg-dt-info/60" : "bg-dt-orange")}
                style={{ width: `${(value / max) * 100}%` }} />
            </span>
            <span className="text-right font-semibold tabular-nums text-dt-text-primary">{fmtNum(value)}</span>
            <ChevronRight className="size-4 text-dt-text-secondary group-hover:text-dt-burnt-orange" aria-hidden />
          </Link>
          <InfoTip text={FLAG_HELP[flag]} label={`What "${FLAG_LABEL[flag]}" means`} />
        </li>
      ))}
    </ul>
  );
}
