"use client";

import { Fragment, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown } from "lucide-react";
import { useMinWidth } from "@/lib/use-media";
import { cx, focusRing } from "./kit";

export type Column<T> = {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  /** Server sort key for this column (`field`; descending is `-field`). */
  sort?: string;
  align?: "left" | "right";
  className?: string;
  /** Hidden below this breakpoint in the table (cards always show everything they render). */
  minWidth?: "lg" | "xl";
};

/** Records as a sticky-header table from md up, and as cards on phones —
 *  never a cramped wide table on a small screen. Optional expandable detail
 *  per row (`detail`) and clickable rows (`onRowClick`). */
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
  const desktop = useMinWidth(768);
  const toggle = (k: string) => setOpen(open === k ? null : k);
  const hide = (c: Column<T>) => (c.minWidth === "lg" ? "hidden lg:table-cell" : c.minWidth === "xl" ? "hidden xl:table-cell" : "");

  if (desktop) return (
      <div className="overflow-hidden rounded-xl border border-dt-border bg-dt-surface">
        <div data-scroll-x className="dt-scrollbar max-h-[70vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{caption}</caption>
            <thead className="sticky top-0 z-10 bg-dt-surface-warm">
              <tr className="border-b border-dt-border">
                {detail && <th scope="col" className="w-10"><span className="sr-only">Details</span></th>}
                {columns.map((c) => (
                  <th key={c.key} scope="col"
                    aria-sort={c.sort && sort ? (sort === c.sort ? "ascending" : sort === `-${c.sort}` ? "descending" : "none") : undefined}
                    className={cx("whitespace-nowrap px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-dt-text-secondary",
                      c.align === "right" && "text-right", hide(c))}>
                    {c.sort && onSort ? (
                      <SortButton label={c.header} field={c.sort} sort={sort} onSort={onSort} align={c.align} />
                    ) : c.header}
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
                      className={cx("border-b border-dt-border/70 last:border-0", (onRowClick || detail) && "cursor-pointer hover:bg-dt-surface-warm/60",
                        isOpen && "bg-dt-surface-warm/60")}
                      onClick={onRowClick ? () => onRowClick(r) : detail ? () => toggle(k) : undefined}
                    >
                      {detail && (
                        <td className="px-2 py-2 align-middle">
                          <button type="button" aria-expanded={isOpen} aria-label={`${isOpen ? "Hide" : "Show"} details${rowLabel ? ` for ${rowLabel(r)}` : ""}`}
                            onClick={(e) => { e.stopPropagation(); toggle(k); }}
                            className={cx("grid size-8 place-items-center rounded-md text-dt-text-secondary hover:bg-dt-surface-warm", focusRing)}>
                            <ChevronDown className={cx("size-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                          </button>
                        </td>
                      )}
                      {columns.map((c, i) => (
                        <td key={c.key} className={cx("px-3 py-2.5 align-middle", c.align === "right" && "text-right tabular-nums", hide(c), c.className)}>
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
                    {detail && isOpen && (
                      <tr className="border-b border-dt-border/70 bg-dt-surface-warm/40">
                        <td colSpan={columns.length + 1} className="px-4 py-3">{detail(r)}</td>
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
          <dd className="truncate text-dt-text-primary">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
