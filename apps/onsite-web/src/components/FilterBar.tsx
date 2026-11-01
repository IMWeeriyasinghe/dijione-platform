"use client";

import { useSite } from "./SiteContext";

const fieldClass =
  "h-9 rounded-lg border border-dt-border bg-dt-surface px-3 text-sm text-dt-text-primary focus:outline-none focus:ring-2 focus:ring-dt-orange/40";

export function SiteSelect() {
  const { sites, site, setSiteId } = useSite();
  if (sites.length < 2) {
    return <span className="text-sm font-medium text-dt-text-primary">{site.name}</span>;
  }
  return (
    <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
      Site
      <select aria-label="Site" className={fieldClass} value={site.site_id} onChange={(e) => setSiteId(e.target.value)}>
        {sites.map((s) => (
          <option key={s.site_id} value={s.site_id}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function DateInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
      {label}
      <input type="date" aria-label={label} className={fieldClass} value={value} onChange={(e) => e.target.value && onChange(e.target.value)} />
    </label>
  );
}

export function TextFilter({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <input
      type="search"
      aria-label={label}
      placeholder={placeholder ?? label}
      className={`${fieldClass} min-w-[12rem]`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function SelectFilter({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <select aria-label={label} className={fieldClass} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function FilterRow({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center gap-3">{children}</div>;
}

export function Pager({ page, pageSize, total, onPage }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-dt-text-secondary">
      <span>{total.toLocaleString()} result{total === 1 ? "" : "s"}</span>
      <div className="flex items-center gap-2">
        <button type="button" className="rounded-md border border-dt-border px-2 py-1 disabled:opacity-40" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button type="button" className="rounded-md border border-dt-border px-2 py-1 disabled:opacity-40" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
