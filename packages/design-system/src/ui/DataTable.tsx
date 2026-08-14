"use client";

import { ChevronLeft, ChevronRight, ChevronsUpDown, ChevronUp, ChevronDown, Search } from "lucide-react";
import { cn } from "../utils";
import { Th } from "./Table";

/** Shared search+sort+pagination primitives (Phase-Next §4) — closes the
 * gap noted in CLAUDE.md §54: every list view previously hand-rolled its
 * own filter bar and pagination heuristic. Built against the stable
 * `{items, total, page, page_size}` envelope every DijiBirthday list
 * endpoint now returns, so "Next" is driven by a real total count instead
 * of a "disable if this page came back short" guess. */

export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm text-dt-text-primary placeholder:text-dt-text-secondary focus:border-dt-orange focus:outline-none focus:ring-1 focus:ring-dt-orange"
      />
    </div>
  );
}

export type SortDirection = "asc" | "desc";

export function SortableTh({
  label,
  sortKey,
  activeSortBy,
  sortDirection,
  onSort,
  className,
}: {
  label: string;
  sortKey: string;
  activeSortBy: string | null;
  sortDirection: SortDirection;
  onSort: (sortKey: string) => void;
  className?: string;
}) {
  const active = activeSortBy === sortKey;
  const Icon = !active ? ChevronsUpDown : sortDirection === "asc" ? ChevronUp : ChevronDown;
  return (
    <Th className={className}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "flex items-center gap-1 uppercase tracking-wide hover:text-dt-text-primary",
          active && "text-dt-text-primary"
        )}
      >
        {label}
        <Icon className="size-3.5" />
      </button>
    </Th>
  );
}

/** Toggles sort_by/sort_direction the way every DijiBirthday list page
 * needs: clicking a new column sorts ascending; clicking the active
 * column again flips direction. */
export function useSortToggle(
  sortBy: string | null,
  sortDirection: SortDirection,
  setSortBy: (v: string | null) => void,
  setSortDirection: (v: SortDirection) => void
) {
  return (key: string) => {
    if (sortBy === key) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDirection("asc");
    }
  };
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="mt-4 flex items-center justify-between">
      <p className="text-sm text-dt-text-secondary">
        {total === 0 ? "No results" : `${start}–${end} of ${total}`}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="flex items-center gap-1 rounded-lg border border-dt-border px-3 py-1.5 text-sm text-dt-text-primary disabled:opacity-40"
        >
          <ChevronLeft className="size-4" />
          Previous
        </button>
        <span className="text-sm text-dt-text-secondary">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="flex items-center gap-1 rounded-lg border border-dt-border px-3 py-1.5 text-sm text-dt-text-primary disabled:opacity-40"
        >
          Next
          <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
}
