"use client";

import { Fragment, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown } from "lucide-react";
import { useMinWidth } from "@/lib/use-media";
import { cx, focusRing, InfoTip } from "./kit";

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  /** Server sort key for this column (`field`; descending is `-field`). */
  sort?: string;
  align?: "left" | "right";
  className?: string;
  /** Explanation shown as an info tip next to the header (never inside the sort button). */
  help?: string;
  /** Table column only from this breakpoint up. Below it the value is not
   *  lost: it moves into the row's expandable details (cards always show
   *  everything they render). */
  minWidth?: "lg" | "xl";
};

/** Records as a sticky-header table from 1024 px up, and as cards below —
 *  never a cramped wide table on a small screen. Columns wrap instead of
 *  forcing a sideways scroll; a column hidden at the current width moves
 *  into the row's expandable details, so every field stays reachable.
 *  Optional expandable detail per row (`detail`) and clickable rows. */
export function DataView<T>({ rows, rowKey, columns, card, detail, onRowClick, sort, onSort, caption, rowLabel }: {
  rows: T[];
  rowKey: (row: T) => string;
  columns: Column<T>[];
  card: (row: T) => React.ReactNode;
  detail?: (row: T) => React.ReactNode;
  onRowClick?: (row: T) => void;
  sort?: string;
  onSort?: (sort: string) => void;
  caption: string;
  rowLabel?: (row: T) => string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const desktop = useMinWidth(1024);
  const wide = useMinWidth(1280);
  const toggle = (k: string) => setOpen(open === k ? null : k);
  const shown = columns.filter((c) => c.minWidth !== "xl" || wide);
  const hidden = columns.filter((c) => !shown.includes(c));
  const rowDetail = hidden.length
    ? (r: T) => (
        <div className="space-y-3">
          {detail?.(r)}
          <Facts cols={4} items={hidden.map((c) => [c.header, c.cell(r)] as [React.ReactNode, React.ReactNode])} />
        </div>
      )
    : detail;

  if (desktop) return (
      <div className="overflow-hidden rounded-xl border border-dt-border bg-dt-surface">
        <div data-scroll-x className="dt-scrollbar max-h-[70vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{caption}</caption>
            <thead className="sticky top-0 z-10 bg-dt-surface-warm">
              <tr className="border-b border-dt-border">
                {rowDetail && <th scope="col" className="w-10"><span className="sr-only">Details</span></th>}
                {shown.map((c) => (
                  <th key={c.key} scope="col"
                    aria-sort={c.sort && sort ? (sort === c.sort ? "ascending" : sort === `-${c.sort}` ? "descending" : "none") : undefined}
                    className={cx("px-2 py-2.5 text-left align-bottom xl:px-3 text-xs font-semibold uppercase leading-tight tracking-wide text-dt-text-secondary",
                      c.align === "right" && "text-right")}>
                    <span className={cx("inline-flex items-center gap-1", c.align === "right" && "flex-row-reverse")}>
                      {c.sort && onSort ? (
                        <SortButton label={c.header} field={c.sort} sort={sort} onSort={onSort} align={c.align} />
                      ) : c.header}
                      {c.help && <InfoTip text={c.help} label={`About ${typeof c.header === "string" ? c.header : "this column"}`} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const k = rowKey(r);
                const isOpen = open === k;
                return (
                  <Fragment key={k}>
                    <tr
                      className={cx("border-b border-dt-border/70 last:border-0", (onRowClick || rowDetail) && "cursor-pointer hover:bg-dt-surface-warm/60",
                        isOpen && "bg-dt-surface-warm/60")}
                      onClick={onRowClick || rowDetail ? (e) => {
                        // Controls inside the row (actions, links) keep their own meaning.
                        if ((e.target as HTMLElement).closest("button, a, input, select, [role='menu']")) return;
                        if (onRowClick) onRowClick(r); else toggle(k);
                      } : undefined}
                    >
                      {rowDetail && (
                        <td className="px-2 py-2 align-middle">
                          <button type="button" aria-expanded={isOpen} aria-label={`${isOpen ? "Hide" : "Show"} details${rowLabel ? ` for ${rowLabel(r)}` : ""}`}
                            onClick={(e) => { e.stopPropagation(); toggle(k); }}
                            className={cx("grid size-8 place-items-center rounded-md text-dt-text-secondary hover:bg-dt-surface-warm", focusRing)}>
                            <ChevronDown className={cx("size-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                          </button>
                        </td>
                      )}
                      {shown.map((c, i) => (
                        <td key={c.key} className={cx("px-2 py-2.5 align-middle break-words xl:px-3", c.align === "right" && "text-right tabular-nums", c.className)}>
                          {i === 0 && onRowClick ? (
                            <button type="button" onClick={(e) => { e.stopPropagation(); onRowClick(r); }}
                              aria-label={rowLabel ? `Open ${rowLabel(r)}` : undefined}
                              className={cx("max-w-full rounded-md text-left", focusRing)}>
                              {c.cell(r)}
                            </button>
                          ) : c.cell(r)}
                        </td>
                      ))}
                    </tr>
                    {rowDetail && isOpen && (
                      <tr className="border-b border-dt-border/70 bg-dt-surface-warm/40">
                        <td colSpan={shown.length + 1} className="px-4 py-3">{rowDetail(r)}</td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
  );

  return (
      <ul className="space-y-2" aria-label={caption}>
        {rows.map((r) => {
          const k = rowKey(r);
          const isOpen = open === k;
          return (
            <li key={k} className="rounded-xl border border-dt-border bg-dt-surface shadow-sm">
              {onRowClick ? (
                <button type="button" onClick={() => onRowClick(r)} className={cx("block w-full rounded-xl p-3 text-left", focusRing)}
                  aria-label={rowLabel ? `Open ${rowLabel(r)}` : undefined}>
                  {card(r)}
                </button>
              ) : (
                <div className="p-3">{card(r)}</div>
              )}
              {detail && (
                <>
                  <button type="button" aria-expanded={isOpen} onClick={() => toggle(k)}
                    className={cx("flex min-h-10 w-full items-center justify-center gap-1 border-t border-dt-border/70 text-xs font-medium text-dt-burnt-orange", focusRing)}>
                    {isOpen ? "Hide details" : "Show details"}
                    <ChevronDown className={cx("size-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                  </button>
                  {isOpen && <div className="border-t border-dt-border/70 p-3">{detail(r)}</div>}
                </>
              )}
            </li>
          );
        })}
      </ul>
  );
}

function SortButton({ label, field, sort, onSort, align }: {
  label: React.ReactNode; field: string; sort?: string; onSort: (s: string) => void; align?: "left" | "right";
}) {
  const active = sort === field || sort === `-${field}`;
  const desc = sort === `-${field}`;
  const Icon = !active ? ArrowUpDown : desc ? ArrowDown : ArrowUp;
  return (
    <button type="button" onClick={() => onSort(active && desc ? field : `-${field}`)}
      className={cx("inline-flex items-center gap-1 rounded uppercase", focusRing, align === "right" && "flex-row-reverse", active && "text-dt-burnt-orange")}>
      {label}
      <Icon className="size-3" aria-hidden />
    </button>
  );
}

/** Label/value pairs for card bodies and expandable details. */
export function Facts({ items, cols = 2 }: { items: [React.ReactNode, React.ReactNode][]; cols?: 2 | 3 | 4 }) {
  return (
    <dl className={cx("grid gap-x-4 gap-y-2 text-sm", cols === 2 ? "grid-cols-2" : cols === 3 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2 sm:grid-cols-4")}>
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs text-dt-text-secondary">{k}</dt>
          <dd className="break-words text-dt-text-primary">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
