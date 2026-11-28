"use client";

import type { ModuleOut } from "@dijione/contracts";
import { cn } from "@dijione/design-system";
import { ArrowRight, Search, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ModuleIcon } from "@/lib/module-icons";

/**
 * Mobile application discovery search for DijiOne Home (shown below sm).
 * On desktop the TopNav search input serves the same role via the
 * `topNavSearch` AppShell prop. Both drive the same `searchQuery` state
 * in page.tsx — zero extra API calls, single source of truth.
 */
export function AppSearch({
  modules,
  query,
  onQueryChange,
  className,
}: {
  modules: ModuleOut[];
  query: string;
  onQueryChange: (q: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [activeIdx, setActiveIdx] = useState(-1);
  const labelId = useId();

  const q = query.trim().toLowerCase();
  const results = q
    ? modules.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q)
      )
    : [];

  const close = useCallback(() => {
    setOpen(false);
    onQueryChange("");
    setActiveIdx(-1);
  }, [onQueryChange]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIdx >= 0) {
      const m = results[activeIdx];
      if (m && m.status !== "COMING_SOON") {
        window.location.href = m.route;
      }
    }
  }

  return (
    <div className={cn("relative mb-6", className)}>
      {/* Search input */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
        <input
          ref={inputRef}
          id={labelId}
          type="search"
          value={query}
          autoComplete="off"
          placeholder="Search apps by name or description…"
          aria-label="Search applications"
          aria-expanded={open && results.length > 0}
          aria-controls={open ? `${labelId}-results` : undefined}
          aria-activedescendant={activeIdx >= 0 ? `${labelId}-result-${activeIdx}` : undefined}
          role="combobox"
          className="w-full rounded-xl border border-dt-border bg-dt-surface py-2.5 pl-9 pr-9 text-sm text-dt-text-primary placeholder:text-dt-text-secondary/70 focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20 sm:max-w-sm"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            onQueryChange(e.target.value);
            setActiveIdx(-1);
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
        {query && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => { onQueryChange(""); inputRef.current?.focus(); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-dt-text-secondary hover:text-dt-text-primary"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>

      {/* Results dropdown */}
      {open && q && (
        <>
          {/* backdrop — closes on outside click */}
          <div className="fixed inset-0 z-10" onClick={close} aria-hidden />
          <ul
            ref={listRef}
            id={`${labelId}-results`}
            role="listbox"
            aria-label="Application search results"
            className="absolute left-0 z-20 mt-1 w-full overflow-hidden rounded-xl border border-dt-border bg-dt-surface shadow-lg sm:max-w-sm"
          >
            {results.length === 0 ? (
              <li className="px-4 py-3 text-sm text-dt-text-secondary">No applications match &ldquo;{query}&rdquo;.</li>
            ) : (
              results.map((m, idx) => {
                const comingSoon = m.status === "COMING_SOON";
                const active = idx === activeIdx;
                return (
                  <li
                    key={m.key}
                    id={`${labelId}-result-${idx}`}
                    role="option"
                    aria-selected={active}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 text-sm transition",
                      comingSoon ? "cursor-default opacity-70" : "cursor-pointer",
                      active && !comingSoon ? "bg-dt-surface-warm" : "hover:bg-dt-surface-warm/60"
                    )}
                    onMouseEnter={() => setActiveIdx(idx)}
                    onClick={() => {
                      if (!comingSoon) window.location.href = m.route;
                    }}
                  >
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-dt-red to-dt-orange text-white">
                      <ModuleIcon iconKey={m.icon} className="size-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-dt-text-primary">{m.name}</p>
                      <p className="truncate text-xs text-dt-text-secondary">{m.description}</p>
                    </div>
                    {comingSoon ? (
                      <span className="shrink-0 rounded-full bg-dt-surface-warm px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-dt-text-secondary">
                        Soon
                      </span>
                    ) : (
                      <ArrowRight className="size-3.5 shrink-0 text-dt-burnt-orange" />
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </>
      )}
    </div>
  );
}
