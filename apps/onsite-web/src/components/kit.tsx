"use client";

// Shared Diji On-site building blocks on the DijiOne design tokens, so every
// page uses one set of patterns: page top, panels, KPI cards, info tips,
// filter panels + chips, segmented controls, avatars, skeletons, empty states
// and a touch-friendly pager.

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronDown, ChevronLeft, ChevronRight, Info, SlidersHorizontal, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getEmployeePhoto } from "@/lib/dashboard";
import { fmtNum } from "@/lib/period";
import { PAGE_SIZES } from "@/lib/page-size";
import { useInView } from "@/lib/use-in-view";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-2 focus-visible:ring-offset-dt-background";

/* ---------------------------------------------------------------- page top */

export function PageTop({ title, description, actions, children }: {
  title: string; description?: React.ReactNode; actions?: React.ReactNode; children?: React.ReactNode;
}) {
  return (
    <header className="mb-4 space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-dt-text-primary sm:text-2xl">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-sm text-dt-text-secondary">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-start gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

/* ------------------------------------------------------------------ panels */

export function Panel({ title, subtitle, action, children, className, bodyClassName, id }: {
  title?: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode;
  className?: string; bodyClassName?: string; id?: string;
}) {
  return (
    <section id={id} className={cx("min-w-0 rounded-xl border border-dt-border bg-dt-surface shadow-sm", className)}>
      {(title || action) && (
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-dt-border/70 px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-dt-text-primary">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-dt-text-secondary">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={cx("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/* --------------------------------------------------------------- info tip */

/** Accessible explanation: hover or keyboard focus shows it; screen readers
 *  get it through aria-describedby. */
export function InfoTip({ text, label = "More information" }: { text: string; label?: string }) {
  const id = useId();
  return (
    <span className="group relative inline-flex">
      <button type="button" aria-label={label} aria-describedby={id}
        className={cx("-m-2.5 rounded-full p-2.5 text-dt-text-secondary hover:text-dt-burnt-orange", focusRing)}>
        <Info className="size-3.5" aria-hidden />
      </button>
      <span id={id} role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-1 hidden w-60 -translate-x-1/2 rounded-lg border border-dt-border bg-dt-surface p-2 text-xs font-normal normal-case leading-snug text-dt-text-primary shadow-lg group-hover:block group-focus-within:block">
        {text}
      </span>
    </span>
  );
}

/* ---------------------------------------------------------------- KPI card */

export type Delta = { value: number; previous: number; label: string } | null;

export function KpiCard({ label, value, icon: Icon, help, delta, href, hrefLabel, tone = "default", sub }: {
  label: string; value: React.ReactNode; icon: LucideIcon; help?: string; delta?: Delta; href?: string;
  hrefLabel?: string; tone?: "default" | "brand" | "attention" | "success" | "danger"; sub?: React.ReactNode;
}) {
  const toneCls = {
    default: "bg-dt-surface-warm text-dt-burnt-orange",
    brand: "bg-dt-red text-white",
    attention: "bg-dt-amber/20 text-dt-warning",
    success: "bg-dt-success/10 text-dt-success",
    danger: "bg-dt-danger/10 text-dt-danger",
  }[tone];
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 items-start gap-1 text-xs font-medium uppercase leading-snug tracking-wide text-dt-text-secondary">
          <span className="line-clamp-2">{label}</span>
          {help && <InfoTip text={help} label={`About ${label}`} />}
        </span>
        <span className={cx("grid size-8 shrink-0 place-items-center rounded-lg", toneCls)}>
          <Icon className="size-4" aria-hidden />
        </span>
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-dt-text-primary">{value}</div>
      <div className="mt-1 flex min-h-5 flex-wrap items-center gap-x-2 text-xs text-dt-text-secondary">
        {delta && <DeltaText {...delta} />}
        {sub}
      </div>
      {href && (
        <span className="mt-2 inline-flex items-center gap-0.5 text-xs font-medium text-dt-burnt-orange">
          {hrefLabel ?? "View records"} <ChevronRight className="size-3" aria-hidden />
        </span>
      )}
    </>
  );
  const cls = "flex min-w-0 flex-col rounded-xl border border-dt-border bg-dt-surface p-4 shadow-sm";
  return href ? (
    <Link href={href} className={cx(cls, "transition-colors hover:border-dt-orange/60 hover:bg-dt-surface-warm/40", focusRing)}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** "+12 vs previous 7 days" — absolute change, with a percentage only when
 *  the previous value is non-zero (no invented infinities). Colour is neutral:
 *  more or less activity is not inherently good or bad. */
export function DeltaText({ value, previous, label }: { value: number; previous: number; label: string }) {
  const diff = value - previous;
  const pct = previous > 0 ? Math.round((diff / previous) * 100) : null;
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  return (
    <span title={`Previous: ${fmtNum(previous)}`}>
      <span className="font-medium text-dt-text-primary">{sign}{fmtNum(Math.abs(diff))}</span>
      {pct !== null && diff !== 0 && <span> ({sign}{Math.abs(pct)}%)</span>} vs {label}
    </span>
  );
}

/* ------------------------------------------------------------ avatar/initials */

const AVATAR_TONES = ["bg-dt-red/10 text-dt-red", "bg-dt-orange/15 text-dt-burnt-orange", "bg-dt-amber/25 text-dt-warning",
  "bg-dt-success/10 text-dt-success", "bg-dt-info/10 text-dt-info"];

export function Initials({ name, code, size = "md", photo = false, alt }: {
  name: string | null | undefined; code: string; size?: "sm" | "md" | "lg";
  /** Request the profile photo (only when the API reports one may exist). */
  photo?: boolean;
  /** Alt text when the photo stands alone; omit when the name is shown beside it. */
  alt?: string;
}) {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  const text = words.length ? (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase() : "#";
  let h = 0;
  for (const ch of code) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const dim = { sm: "size-8 text-xs", md: "size-9 text-sm", lg: "size-12 text-base" }[size];
  return (
    <span className={cx("relative grid shrink-0 place-items-center overflow-hidden rounded-full font-semibold", dim,
      name ? AVATAR_TONES[h % AVATAR_TONES.length] : "border border-dashed border-dt-border text-dt-text-secondary")}>
      <span aria-hidden>{text}</span>
      {photo && <EmployeePhoto code={code} alt={alt} />}
    </span>
  );
}

/** Lazy profile photo layered over the initials: requested only once the
 *  avatar is near the viewport, cached per employee for the session (never
 *  refetched by the 30-second dashboard refresh), and silently absent on any
 *  failure — the initials underneath simply stay visible. */
function EmployeePhoto({ code, alt }: { code: string; alt?: string }) {
  const [ref, inView] = useInView<HTMLSpanElement>();
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const query = useQuery({
    queryKey: ["onsite-photo", code],
    queryFn: () => getEmployeePhoto(code),
    enabled: inView,
    staleTime: Infinity,
    gcTime: 60 * 60_000,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return (
    <span ref={ref} className="absolute inset-0">
      {query.data && !failed && (
        // eslint-disable-next-line @next/next/no-img-element -- blob URL from an authenticated fetch
        <img src={query.data} alt={alt ?? ""} aria-hidden={alt ? undefined : true} onError={() => setFailed(true)} onLoad={() => setLoaded(true)}
          className={cx("size-full rounded-full object-cover motion-safe:transition-opacity", loaded ? "opacity-100" : "opacity-0")} />
      )}
    </span>
  );
}

export function Person({ name, code, meta, size = "md", photo = false }: {
  name: string | null | undefined; code: string; meta?: React.ReactNode; size?: "sm" | "md" | "lg"; photo?: boolean;
}) {
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <Initials name={name} code={code} size={size} photo={photo} />
      <span className="min-w-0">
        <span className="block truncate font-medium text-dt-text-primary">{name ?? "Unmatched code"}</span>
        <span className="block truncate text-xs text-dt-text-secondary">
          <span aria-hidden>#</span><span className="font-mono">{code}</span>{meta ? <> · {meta}</> : null}
        </span>
      </span>
    </span>
  );
}

/* ------------------------------------------------------- loading / empty */

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cx("block rounded-md bg-dt-border/50 motion-safe:animate-pulse", className)} />;
}

export function SkeletonRows({ rows = 6, label = "Loading…" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-12 w-full" />)}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyPanel({ icon: Icon, title, description, actions }: {
  icon: LucideIcon; title: string; description?: React.ReactNode; actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-dt-surface-warm text-dt-burnt-orange">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="mt-3 font-medium text-dt-text-primary">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-dt-text-secondary">{description}</p>}
      {actions && <div className="mt-4 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}

export function InlineAlert({ tone = "warning", children, action }: {
  tone?: "warning" | "danger" | "info"; children: React.ReactNode; action?: React.ReactNode;
}) {
  const cls = {
    warning: "border-dt-amber/50 bg-dt-amber/10 text-dt-text-primary",
    danger: "border-dt-danger/30 bg-dt-danger/5 text-dt-text-primary",
    info: "border-dt-border bg-dt-surface-warm text-dt-text-primary",
  }[tone];
  return (
    <div role={tone === "info" ? "note" : "alert"} className={cx("flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm", cls)}>
      <span>{children}</span>
      {action}
    </div>
  );
}

/* ----------------------------------------------------------------- buttons */

export function LinkButton({ href, children, variant = "secondary" }: {
  href: string; children: React.ReactNode; variant?: "primary" | "secondary" | "ghost";
}) {
  return <Link href={href} className={buttonClass(variant)}>{children}</Link>;
}

export function buttonClass(variant: "primary" | "secondary" | "ghost" = "secondary"): string {
  return cx(
    "inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors md:min-h-9",
    focusRing,
    variant === "primary" && "bg-dt-red text-white hover:bg-dt-red/90",
    variant === "secondary" && "border border-dt-border bg-dt-surface text-dt-text-primary hover:bg-dt-surface-warm",
    variant === "ghost" && "text-dt-burnt-orange hover:bg-dt-surface-warm",
  );
}

/* ------------------------------------------------------- segmented control */

export function Segmented<T extends string>({ label, value, options, onChange, size = "md" }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} data-scroll-x className="dt-scrollbar inline-flex min-w-0 max-w-full gap-1 overflow-x-auto rounded-lg border border-dt-border bg-dt-surface p-1">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}
          className={cx("shrink-0 whitespace-nowrap rounded-md px-3 font-medium transition-colors", focusRing,
            size === "sm" ? "min-h-8 text-xs" : "min-h-9 text-sm",
            value === o.value ? "bg-dt-cream text-dt-burnt-orange shadow-sm" : "text-dt-text-secondary hover:bg-dt-surface-warm")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ filters */

export const fieldClass = cx(
  "h-10 w-full min-w-0 rounded-lg border border-dt-border bg-dt-surface px-3 text-sm text-dt-text-primary md:h-9",
  "focus:outline-none focus:ring-2 focus:ring-dt-orange/40",
);

export function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cx("flex min-w-0 flex-col gap-1 text-xs font-medium text-dt-text-secondary", className)}>
      {label}
      {children}
    </label>
  );
}

export type Chip = { key: string; label: string; onClear: () => void };

/** A filter panel: the fields collapse behind a "Filters" toggle on small
 *  screens; active filters are always visible as removable chips. */
export function FilterPanel({ children, chips, onClearAll, summary }: {
  children: React.ReactNode; chips: Chip[]; onClearAll?: () => void; summary?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 md:hidden">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className={buttonClass("secondary")}>
          <SlidersHorizontal className="size-4" aria-hidden /> Filters{chips.length ? ` (${chips.length})` : ""}
          <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
        {summary}
      </div>
      <div className={cx("grid grid-cols-1 gap-3 rounded-xl border border-dt-border bg-dt-surface p-3 sm:grid-cols-2 md:grid md:grid-cols-3 xl:grid-cols-6",
        open ? "grid" : "hidden")}>
        {children}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {chips.map((c) => (
            <span key={c.key} className="inline-flex items-center gap-1 rounded-full border border-dt-orange/40 bg-dt-cream py-0.5 pl-3 pr-1 text-xs text-dt-burnt-orange">
              {c.label}
              <button type="button" aria-label={`Remove filter: ${c.label}`} onClick={c.onClear}
                className={cx("grid size-6 place-items-center rounded-full hover:bg-dt-orange/15", focusRing)}>
                <X className="size-3" aria-hidden />
              </button>
            </span>
          ))}
          {onClearAll && chips.length > 1 && (
            <button type="button" onClick={onClearAll} className={cx("min-h-8 rounded-md px-2 text-xs font-medium text-dt-burnt-orange underline underline-offset-2", focusRing)}>
              Clear all
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- pager */

/** Server-side pagination controls: range ("1–10 of 506 employees"),
 *  previous/next, page x of y and a page-size choice (10/20/50/100). On
 *  phones the page counter is condensed; nothing is removed. */
export function Pager({ page, pageSize, total, onPage, onPageSize, noun = "result", busy = false }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void;
  onPageSize?: (size: number) => void; noun?: string; busy?: boolean;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pagination" aria-busy={busy || undefined}
      className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-dt-text-secondary">
      <span aria-live="polite">{total ? `${fmtNum(first)}–${fmtNum(last)} of ${fmtNum(total)} ${noun}${total === 1 ? "" : "s"}` : `0 ${noun}s`}</span>
      <span className="flex flex-wrap items-center gap-2">
        {onPageSize && (
          <label className="flex items-center gap-1.5 whitespace-nowrap text-xs">
            <span className="hidden sm:inline">Rows per page</span><span className="sm:hidden">Rows</span>
            <select aria-label="Rows per page" value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}
              className={cx(fieldClass, "w-auto")}>
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <span className="flex items-center gap-1">
          <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}
            className={cx(buttonClass("secondary"), "px-2 disabled:opacity-40")}>
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <span className="px-1 tabular-nums" aria-current="page">
            <span className="hidden sm:inline">Page </span>{page}<span className="hidden sm:inline"> of </span><span className="sm:hidden">/</span>{pages}
          </span>
          <button type="button" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}
            className={cx(buttonClass("secondary"), "px-2 disabled:opacity-40")}>
            <ChevronRight className="size-4" aria-hidden />
          </button>
        </span>
      </span>
    </nav>
  );
}
