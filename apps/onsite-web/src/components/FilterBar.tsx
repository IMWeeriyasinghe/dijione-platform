"use client";

import { useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, MapPin, Search } from "lucide-react";
import { addDays } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { fmtDay, MAX_RANGE_DAYS, normalizePeriod, type Period, presetOf, presetPeriod, PRESETS } from "@/lib/period";
import type { IdentityClass } from "@/lib/types";
import { buttonClass, cx, Field, fieldClass, focusRing, Segmented } from "./kit";
import { useSite } from "./SiteContext";

export { fieldClass };

/** Site picker; with a single enabled site it is a plain label. */
export function SiteSelect() {
  const { sites, site, setSiteId } = useSite();
  if (sites.length < 2) {
    return (
      <span className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-dt-border bg-dt-surface px-3 text-sm font-medium text-dt-text-primary">
        <MapPin className="size-4 text-dt-burnt-orange" aria-hidden /> {site.name}
      </span>
    );
  }
  return (
    <label className="inline-flex items-center gap-1.5 text-sm">
      <MapPin className="size-4 text-dt-burnt-orange" aria-hidden />
      <span className="sr-only">Site</span>
      <select aria-label="Site" className={cx(fieldClass, "w-auto font-medium")} value={site.site_id} onChange={(e) => setSiteId(e.target.value)}>
        {sites.map((s) => <option key={s.site_id} value={s.site_id}>{s.name}</option>)}
      </select>
    </label>
  );
}

/** Period presets (Today / Yesterday / Last 7 / Last 30) plus a custom range.
 *  `today` is the site-local date from onsite-api. */
export function PeriodControl({ value, onChange, today, allowSingleDayOnly = false }: {
  value: Period; onChange: (p: Period) => void; today: string; allowSingleDayOnly?: boolean;
}) {
  const [customMode, setCustomMode] = useState(false);
  const preset = customMode ? "custom" : presetOf(value, today);
  const options = PRESETS.filter((p) => !allowSingleDayOnly || p.key === "today" || p.key === "yesterday")
    .map((p) => ({ value: p.key as string, label: p.label }));
  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-end gap-2">
      <Segmented label="Period" value={preset} options={[...options, { value: "custom", label: "Custom" }]}
        onChange={(k) => {
          setCustomMode(k === "custom");
          if (k !== "custom") onChange(presetPeriod(k as Exclude<typeof preset, "custom">, today));
        }} />
      {preset === "custom" && (
        <div className="flex flex-wrap items-center gap-2">
          <DateField label="From" value={value.from} max={today} onChange={(v) => onChange(normalizePeriod({ from: v, to: value.to }))} />
          <span aria-hidden className="text-dt-text-secondary">–</span>
          <DateField label="To" value={value.to} max={today} onChange={(v) => onChange(normalizePeriod({ from: value.from, to: v }))} />
        </div>
      )}
      <span className="sr-only">Ranges are limited to {MAX_RANGE_DAYS} days.</span>
    </div>
  );
}

function DateField({ label, value, onChange, max }: { label: string; value: string; onChange: (v: string) => void; max?: string }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs font-medium text-dt-text-secondary">
      {label}
      <input type="date" aria-label={label} className={cx(fieldClass, "w-38")} value={value} max={max}
        onChange={(e) => e.target.value && onChange(e.target.value)} />
    </label>
  );
}

/** A single site-local day with previous/next stepping and quick jumps. */
export function DayControl({ value, onChange, today, latest }: {
  value: string; onChange: (d: string) => void; today: string; latest?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex items-center rounded-lg border border-dt-border bg-dt-surface">
        <button type="button" aria-label="Previous day" onClick={() => onChange(addDays(value, -1))}
          className={cx("grid size-10 place-items-center rounded-l-lg text-dt-text-secondary hover:bg-dt-surface-warm md:size-9", focusRing)}>
          <ChevronLeft className="size-4" aria-hidden />
        </button>
        <label className="relative flex items-center">
          <span className="sr-only">Date</span>
          <CalendarDays className="pointer-events-none absolute left-2 size-4 text-dt-burnt-orange" aria-hidden />
          <input type="date" aria-label="Date" value={value} max={today} onChange={(e) => e.target.value && onChange(e.target.value)}
            className="h-10 w-42 border-x border-dt-border bg-transparent pl-8 pr-2 text-sm font-medium text-dt-text-primary focus:outline-none focus:ring-2 focus:ring-dt-orange/40 md:h-9" />
        </label>
        <button type="button" aria-label="Next day" disabled={value >= today} onClick={() => onChange(addDays(value, 1))}
          className={cx("grid size-10 place-items-center rounded-r-lg text-dt-text-secondary hover:bg-dt-surface-warm disabled:opacity-40 md:size-9", focusRing)}>
          <ChevronRight className="size-4" aria-hidden />
        </button>
      </div>
      {value !== today && (
        <button type="button" onClick={() => onChange(today)} className={buttonClass("ghost")}>Today</button>
      )}
      {latest && latest !== value && latest !== today && (
        <button type="button" onClick={() => onChange(latest)} className={buttonClass("ghost")}>
          Latest activity ({fmtDay(latest)})
        </button>
      )}
    </div>
  );
}

export function SearchField({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <Field label={label}>
      <span className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" aria-hidden />
        <input type="search" aria-label={label} placeholder={placeholder ?? label} value={value} onChange={(e) => onChange(e.target.value)}
          className={cx(fieldClass, "pl-8")} />
      </span>
    </Field>
  );
}

export function SelectField({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <Field label={label}>
      <select aria-label={label} className={fieldClass} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Field>
  );
}

export const IDENTITY_CLASSES: IdentityClass[] = ["MATCHED_ACTIVE", "MATCHED_INACTIVE", "MATCHED_BEFORE_HIRE", "AMBIGUOUS", "UNMATCHED"];

export function IdentitySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <SelectField label="Identity match" value={value} onChange={onChange}
      options={[{ value: "", label: "All identities" }, ...IDENTITY_CLASSES.map((c) => ({ value: c, label: IDENTITY_LABEL[c] }))]} />
  );
}

/** Departments come from the Workforce Directory (via onsite-api); used for
 *  filtering and display only, never for identity matching. */
export function DepartmentSelect({ value, onChange, departments }: {
  value: string; onChange: (v: string) => void; departments?: string[];
}) {
  const { site } = useSite();
  const list = site.departments?.length ? site.departments : departments ?? [];
  return (
    <SelectField label="Department" value={value} onChange={onChange}
      options={[{ value: "", label: "All departments" }, ...list.map((d) => ({ value: d, label: d }))]} />
  );
}
