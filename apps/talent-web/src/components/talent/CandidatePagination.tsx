"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

/** Page numbers to show around the current page, with "…" gaps. */
export function pageWindow(page: number, totalPages: number, radius = 1): (number | "gap")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const pages = new Set([1, totalPages]);
  for (let p = page - radius; p <= page + radius; p++) if (p >= 1 && p <= totalPages) pages.add(p);
  const sorted = [...pages].sort((a, b) => a - b);
  const out: (number | "gap")[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push("gap");
    out.push(p);
  });
  return out;
}

// Colour classes live in exactly one state set below, so an element never
// carries two competing utilities for the same property — Tailwind orders
// same-property utilities by name, not by class order, which is why the old
// "bg-dt-surface ... bg-dt-orange text-white" active page rendered
// white-on-white. The active outline is an inset ring (box-shadow), not a
// border colour: talent-web's globals.css has an unlayered
// `* { border-color: var(--dt-border) }` that overrides every border-dt-*
// utility. Focus uses `outline` so it never fights the active ring.
const base =
  "inline-flex min-w-9 items-center justify-center gap-1 rounded-lg border px-2.5 py-1.5 text-sm transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-dt-orange";
const idle =
  "bg-dt-surface text-dt-text-primary hover:bg-dt-surface-warm disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-dt-surface";
const active = "bg-dt-orange/10 font-bold text-dt-text-primary ring-2 ring-inset ring-dt-orange";
const btn = `${base} ${idle}`;

export function CandidatePagination({
  page,
  pageSize,
  pageSizes,
  total,
  totalPages,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  pageSizes: readonly number[];
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const atFirst = page <= 1;
  const atLast = page >= totalPages;

  return (
    <nav
      aria-label="Candidate pagination"
      className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
    >
      <div className="flex flex-wrap items-center gap-3 text-sm text-dt-text-secondary">
        <span aria-live="polite">
          {total === 0
            ? "No candidates"
            : `Showing ${start}–${end} of ${total.toLocaleString()} candidate${total === 1 ? "" : "s"}`}
        </span>
        <label className="flex items-center gap-2">
          <span>Per page</span>
          <select
            aria-label="Candidates per page"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded-lg border border-dt-border bg-dt-surface px-2 py-1 text-sm text-dt-text-primary focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          >
            {pageSizes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={btn} disabled={atFirst} onClick={() => onPageChange(1)} aria-label="First page">
          <ChevronsLeft className="size-4" />
        </button>
        <button type="button" className={btn} disabled={atFirst} onClick={() => onPageChange(page - 1)} aria-label="Previous page">
          <ChevronLeft className="size-4" />
          <span className="hidden sm:inline">Previous</span>
        </button>

        {/* Numbered pages: full window on ≥sm, compact "page / total" on mobile. */}
        <span className="px-2 text-sm text-dt-text-secondary sm:hidden">
          Page {page} of {totalPages}
        </span>
        <span className="hidden items-center gap-1.5 sm:flex">
          {pageWindow(page, totalPages).map((p, i) =>
            p === "gap" ? (
              <span key={`gap-${i}`} className="px-1 text-dt-text-secondary" aria-hidden>
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPageChange(p)}
                aria-label={`Page ${p}`}
                aria-current={p === page ? "page" : undefined}
                className={p === page ? `${base} ${active}` : btn}
              >
                {p}
              </button>
            )
          )}
        </span>

        <button type="button" className={btn} disabled={atLast} onClick={() => onPageChange(page + 1)} aria-label="Next page">
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" />
        </button>
        <button type="button" className={btn} disabled={atLast} onClick={() => onPageChange(totalPages)} aria-label="Last page">
          <ChevronsRight className="size-4" />
        </button>
      </div>
    </nav>
  );
}
