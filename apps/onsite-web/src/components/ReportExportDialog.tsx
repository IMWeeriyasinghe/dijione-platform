"use client";

import { useState } from "react";
import { Button, Modal } from "@dijione/design-system";
import { FileSpreadsheet } from "lucide-react";
import { cx, Field, fieldClass, InlineAlert } from "@/components/kit";
import { downloadExport, VIEWER_REVIEW_FLAGS, type ExportPath, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_LABEL } from "@/lib/flags";
import { FINGERPRINT_DISCLAIMER, MAPPING_FILTER_OPTIONS } from "@/lib/format";
import { REVIEW_STATUS_FILTERS } from "@/lib/reviews";

export type ReportType = "recorded" | "verified" | "daily" | "team" | "exceptions" | "overview";
type Filter = "identity" | "zk" | "mapping" | "department" | "terminal" | "flag" | "review" | "detail";

/** Each report lists only the filters its endpoint supports. */
export const REPORTS: Record<ReportType, { label: string; path: ExportPath; description: string; filters: Filter[]; singleDay?: boolean }> = {
  daily: { label: "Daily Fingerprint Activity Summary", path: "activity/daily", filters: ["identity", "zk", "mapping", "terminal", "review", "detail"],
    description: "One row per identity-day for verified, unmapped and conflict IDs: first / last recorded fingerprint, Recorded Span and punches, with the administrative review in a separate column group." },
  recorded: { label: "Recorded Activity (raw events)", path: "activity", filters: ["identity", "zk", "mapping", "department", "terminal"],
    description: "Every recorded fingerprint event of the selected mapping states, with its whole-day sequence. Unverified events show the raw ZKBioTime ID only." },
  verified: { label: "Verified Attendance", path: "activity", filters: ["identity", "zk", "department", "terminal", "flag"],
    description: "Verified team-member days and their events only (unmapped activity is counted in the summary, never attributed)." },
  team: { label: "Team Member Attendance", path: "employees", filters: ["identity", "zk", "department"],
    description: "One row per verified team member: activity days, recorded events, review flags and last recorded fingerprint." },
  exceptions: { label: "Exceptions", path: "exceptions", filters: ["identity", "zk", "department", "flag"],
    description: "Verified team-member days with review flags, their reasons and the administrative review columns." },
  overview: { label: "Overview summary (single day)", path: "dashboard/overview", filters: [], singleDay: true,
    description: "The day's KPIs, recorded events by mapping state, Earliest / Latest Recorded Fingerprint, hourly and 30-day trend." },
};

export type ExportContext = {
  report: ReportType; siteId: string; today: string; from: string; to: string;
  q?: string; emp?: string; mapping?: string; dept?: string; term?: string; flag?: string; review?: string;
};

const RANGES = [
  { value: "page", label: "As on the page" }, { value: "today", label: "Today" }, { value: "yesterday", label: "Yesterday" },
  { value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "custom", label: "Custom (up to 92 days)" },
];

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(`${b}T00:00:00Z`).getTime() - new Date(`${a}T00:00:00Z`).getTime()) / 86_400_000) + 1;
}

/** Builds the export request for a report (exported for tests). */
export function exportRequest(report: ReportType, v: Required<Omit<ExportContext, "report">> & { detail: string }): { path: ExportPath; params: Record<string, string | undefined> } {
  const r = REPORTS[report];
  const has = (f: Filter) => r.filters.includes(f);
  const params: Record<string, string | undefined> = { site_id: v.siteId };
  if (r.singleDay) params.date = v.to;
  else Object.assign(params, { date_from: v.from, date_to: v.to });
  if (has("identity")) params.q = v.q || undefined;
  if (has("zk")) params.emp_code = v.emp.trim() || undefined;
  if (has("mapping")) params.mapping = v.mapping || "all";
  if (has("department")) params.department = v.dept || undefined;
  if (has("terminal")) params.terminal = v.term || undefined;
  if (has("flag")) params.flag = v.flag || undefined;
  if (has("review")) params.review_status = v.review || undefined;
  if (has("detail")) params.detail = v.detail;
  if (report === "verified") params.mapping = "verified";
  return { path: r.path, params };
}

export function ReportExportDialog({ context, departments = [], terminals = [], onClose }: {
  context: ExportContext; departments?: string[]; terminals?: string[]; onClose: () => void;
}) {
  const [report, setReport] = useState<ReportType>(context.report);
  const [range, setRange] = useState("page");
  const [from, setFrom] = useState(context.from);
  const [to, setTo] = useState(context.to);
  const [q, setQ] = useState(context.q ?? "");
  const [emp, setEmp] = useState(context.emp ?? "");
  const [mapping, setMapping] = useState(context.mapping || "all");
  const [dept, setDept] = useState(context.dept ?? "");
  const [term, setTerm] = useState(context.term ?? "");
  const [flag, setFlag] = useState(context.flag ?? "");
  const [review, setReview] = useState(context.review ?? "");
  const [detail, setDetail] = useState("both");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const r = REPORTS[report];
  const has = (f: Filter) => r.filters.includes(f);

  const period = (() => {
    const t = context.today;
    switch (range) {
      case "today": return { from: t, to: t };
      case "yesterday": return { from: addDays(t, -1), to: addDays(t, -1) };
      case "7": return { from: addDays(t, -6), to: t };
      case "30": return { from: addDays(t, -29), to: t };
      case "custom": return { from, to };
      default: return { from: context.from, to: context.to };
    }
  })();
  const span = daysBetween(period.from, period.to);
  const invalid = !period.from || !period.to || span < 1 ? "Choose a valid date range."
    : span > 92 ? "The date range is limited to 92 days."
    : r.singleDay && span > 1 ? "The Overview summary covers a single day: the last day of the range is used." : null;
  const blocking = invalid && !invalid.startsWith("The Overview");

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const req = exportRequest(report, { siteId: context.siteId, today: context.today, from: period.from, to: period.to, q, emp,
        mapping, dept, term, flag, review, detail });
      await downloadExport(req.path, req.params);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const sel = (label: string, value: string, set: (v: string) => void, options: readonly { value: string; label: string }[]) => (
    <Field label={label}>
      <select aria-label={label} className={fieldClass} value={value} onChange={(e) => set(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Field>
  );

  return (
    <Modal open onClose={onClose} title="Export report">
      <form className="max-h-[75vh] space-y-3 overflow-y-auto pr-1" onSubmit={(e) => { e.preventDefault(); if (!blocking) void run(); }}>
        {sel("Report type", report, (v) => setReport(v as ReportType), (Object.keys(REPORTS) as ReportType[]).map((k) => ({ value: k, label: REPORTS[k].label })))}
        <p className="text-sm text-dt-text-secondary">{r.description}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {sel("Date range", range, setRange, RANGES)}
          {range === "custom" && (
            <>
              <Field label="From"><input aria-label="From" type="date" className={fieldClass} value={from} max={context.today} onChange={(e) => setFrom(e.target.value)} /></Field>
              <Field label="To"><input aria-label="To" type="date" className={fieldClass} value={to} max={context.today} onChange={(e) => setTo(e.target.value)} /></Field>
            </>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {has("identity") && (
            <Field label="Team member (name, BHR ID or EMP Number)">
              <input aria-label="Team member (name, BHR ID or EMP Number)" className={fieldClass} value={q} onChange={(e) => setQ(e.target.value)} placeholder="All team members" />
            </Field>
          )}
          {has("zk") && (
            <Field label="ZKBioTime ID (exact)">
              <input aria-label="ZKBioTime ID (exact)" className={fieldClass} value={emp} onChange={(e) => setEmp(e.target.value)} placeholder="All IDs" />
            </Field>
          )}
          {has("mapping") && sel("Mapping status", mapping, setMapping, MAPPING_FILTER_OPTIONS)}
          {has("department") && sel("Department", dept, setDept, [{ value: "", label: "All departments" }, ...departments.map((d) => ({ value: d, label: d }))])}
          {has("terminal") && sel("Terminal", term, setTerm, [{ value: "", label: "All terminals" }, ...terminals.map((t) => ({ value: t, label: t }))])}
          {has("flag") && sel("Exception category", flag, setFlag, [{ value: "", label: "Any" }, ...VIEWER_REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f as ReviewFlag] }))])}
          {has("review") && sel("Review status", review, setReview, REVIEW_STATUS_FILTERS)}
          {has("detail") && sel("Detail level", detail, setDetail, [
            { value: "summary", label: "Summary (one row per identity-day)" },
            { value: "detailed", label: "Detailed (every fingerprint + case history)" },
            { value: "both", label: "Both" },
          ])}
        </div>
        <p className="text-xs text-dt-text-secondary">{FINGERPRINT_DISCLAIMER} Every filter and your site access are re-applied by the server.</p>
        {invalid && <InlineAlert tone={blocking ? "danger" : "warning"}>{invalid}</InlineAlert>}
        {error && <p role="alert" className="text-sm text-dt-danger">{error}</p>}
        <div className={cx("flex flex-wrap justify-end gap-2")}>
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy || Boolean(blocking)}>
            <FileSpreadsheet className="size-4" aria-hidden /> {busy ? "Preparing…" : "Export to Excel"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** "Export report…" — opens the dialog prefilled from the page. */
export function ExportReportButton(props: { context: ExportContext; departments?: string[]; terminals?: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <FileSpreadsheet className="size-4" aria-hidden /> Export report…
      </Button>
      {open && <ReportExportDialog {...props} onClose={() => setOpen(false)} />}
    </>
  );
}
