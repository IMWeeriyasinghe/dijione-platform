/* Diji On-site v0.9: Daily summary, Earliest / Latest Recorded Fingerprint,
 * report export dialog, attendance review dialog, DataView flow, palette and
 * entry-only fingerprint wording. Synthetic data only. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@dijione/auth-client";
import { setTestUrl } from "@/test-navigation";

const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } as { role: string; permissions: string[] } | null } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scope.value };
});
const api = vi.hoisted(() => ({
  getSitesInfo: vi.fn(), getOverview: vi.fn(), getHourly: vi.fn(), getTrend: vi.fn(), getRecent: vi.fn(),
  getActivity: vi.fn(), getDailyActivity: vi.fn(), downloadExport: vi.fn(), getReviewDay: vi.fn(), openReview: vi.fn(),
  submitReview: vi.fn(), resolveReview: vi.fn(), reopenReview: vi.fn(),
}));
vi.mock("@/lib/dashboard", async (orig) => ({ ...(await orig<typeof import("@/lib/dashboard")>()), ...api }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), requestSync: vi.fn(), getSyncRun: vi.fn(),
  getFreshness: vi.fn().mockResolvedValue({ source_configured: true, last_successful_sync_at: new Date().toISOString(), latest_run: null,
    sites: [{ site_id: "dev-site", feed_state: "FRESH", latest_received_utc: null, latest_punch_utc: null, agent_heartbeat_utc: null, agent_health: null }] }),
}));

const SITE = { site_id: "dev-site", name: "DEV Site (Colombo)", time_zone: "Asia/Colombo", today: "2026-11-18",
  first_activity_date: "2024-11-27", last_activity_date: "2026-11-18", terminals: ["Main Door"] };
const ROW = (o: Record<string, unknown>) => ({
  site_id: "dev-site", local_date: "2026-11-17", time_zone: "Asia/Colombo", identity_kind: "PERSON", mapping_state: "VERIFIED",
  emp_code: "9001", zk_emp_codes: ["9001"], bamboohr_id: "B1", employee_number: "E-1", employee_name: "Verified Person",
  department: "Ops", employment_status: "Active", has_photo: false, mapping_status: "MAPPED", identity_key: "P:B1",
  first_fingerprint_local: "2026-11-17T08:30:00+05:30", last_fingerprint_local: "2026-11-17T17:45:00+05:30", punch_count: 4,
  recorded_span_minutes: 555, single: false, terminal_names: ["Main Door"], review: null, ...o });
const DAILY = {
  total: 3, page: 1, page_size: 10, date_from: "2026-11-12", date_to: "2026-11-18", time_zone: "Asia/Colombo", mapping: "all",
  directory_available: true, can_manage_reviews: false,
  summary: { identity_days: 3, punches: 6, single_fingerprint_days: 2, verified_identity_days: 1, unmapped_identity_days: 1,
    conflict_identity_days: 1, verified_punches: 4, unmapped_punches: 1, conflict_punches: 1 },
  items: [
    ROW({}),
    ROW({ identity_key: "C:352", identity_kind: "CODE", mapping_state: "UNMAPPED", emp_code: "352", zk_emp_codes: ["352"],
      bamboohr_id: null, employee_number: null, employee_name: null, mapping_status: "UNMAPPED", punch_count: 1, single: true,
      recorded_span_minutes: null, last_fingerprint_local: "2026-11-17T09:05:00+05:30", first_fingerprint_local: "2026-11-17T09:05:00+05:30",
      review: { id: 7, status: "SUBMITTED", exception_type: "SINGLE_RECORDED_FINGERPRINT", justification_reason: "ASSIGNED_OFF_SITE",
        outcome: null, estimated_minutes: null, declared_departure_local: null, reviewer: "Admin", reviewed_at: "2026-11-18T01:00:00Z",
        version: 2, duration_verified: false, stale: true, reassess_reasons: ["IDENTITY_CHANGED"], identity_changed: true } }),
    ROW({ identity_key: "C:77", identity_kind: "CODE", mapping_state: "CONFLICT", emp_code: "77", zk_emp_codes: ["77"], bamboohr_id: null,
      employee_number: null, employee_name: null, mapping_status: "MAPPING_CONFLICT", punch_count: 1, single: true, recorded_span_minutes: null }),
  ],
};

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  scope.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } };
  api.getSitesInfo.mockResolvedValue([SITE]);
  api.getDailyActivity.mockResolvedValue(DAILY);
  api.getActivity.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
});

describe("Activity Daily summary (all identities)", () => {
  it("is the default view and shows verified, unmapped and conflict identity-days", async () => {
    setTestUrl("/activity");
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    const table = await screen.findByRole("table", { name: "Daily fingerprint activity by identity" });
    expect(api.getActivity).not.toHaveBeenCalled();
    expect(api.getDailyActivity).toHaveBeenCalledWith(expect.objectContaining({ mapping: "all", sort: "-date" }));
    expect(within(table).getByText("Verified Person")).toBeInTheDocument();
    expect(within(table).getByText("ZKBioTime ID 352")).toBeInTheDocument();
    expect(within(table).getByText("ZKBioTime ID 77")).toBeInTheDocument();
    expect(within(table).getByText("9h 15m")).toBeInTheDocument(); // Recorded Span
    // Single fingerprint: span unavailable (never 0h), neutral chip, never an exit.
    expect(within(table).queryByText(/0h/)).not.toBeInTheDocument();
    expect(within(table).getAllByText("Single Recorded Fingerprint").length).toBeGreaterThan(0);
    expect(within(table).getByText("Justification submitted")).toBeInTheDocument();
    expect(within(table).getByText("Needs reassessment")).toBeInTheDocument();
    for (const h of ["First Recorded Fingerprint", "Last Recorded Fingerprint", "Recorded Span"]) {
      expect(within(table).getByRole("columnheader", { name: new RegExp(h) })).toBeInTheDocument();
    }
    const cards = screen.getByRole("group", { name: "Identity-days by mapping status" });
    expect(within(cards).getByText("4 fingerprints")).toBeInTheDocument();
  });

  it("switches to Events and back through the URL", async () => {
    setTestUrl("/activity");
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    await screen.findByRole("table", { name: "Daily fingerprint activity by identity" });
    fireEvent.click(within(screen.getByRole("group", { name: "View" })).getByRole("button", { name: "Events" }));
    await waitFor(() => expect(api.getActivity).toHaveBeenCalled());
  });

  it("opens a read-only case for an On-site User", async () => {
    api.getReviewDay.mockResolvedValue({ case: null, history: [], can_manage: false, punches: [
      { position: 1, of: 1, local_time: "2026-11-17T09:05:00+05:30", zk_emp_code: "77", terminal: "Main Door", sequence: "SINGLE" }],
      current_facts: { punch_count: 1, first_utc: null, last_utc: null, first_local: "2026-11-17T09:05:00+05:30",
        last_local: "2026-11-17T09:05:00+05:30", recorded_span_minutes: null, events_hash: "x", mapping: { state: "CONFLICT", zk_emp_codes: ["77"], mapping_ids: [] } } });
    setTestUrl("/activity");
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    const table = await screen.findByRole("table", { name: "Daily fingerprint activity by identity" });
    fireEvent.click(within(table).getAllByRole("button", { name: "View day" }).at(-1)!); // the conflict ID 77
    expect(await screen.findByText("Recorded evidence (current)")).toBeInTheDocument();
    expect(api.getReviewDay).toHaveBeenCalledWith(expect.objectContaining({ zk_emp_code: "77" }));
    expect(screen.getByText("—, Single Recorded Fingerprint")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open review case" })).not.toBeInTheDocument();
  });
});

describe("AttendanceReviewDialog (On-site Admin)", () => {
  const facts = { punch_count: 2, first_utc: null, last_utc: null, first_local: "2026-11-17T08:30:00+05:30",
    last_local: "2026-11-17T17:30:00+05:30", recorded_span_minutes: 540, events_hash: "h", mapping: { state: "VERIFIED", zk_emp_codes: ["9001"], mapping_ids: [1] } };
  const CASE = { id: 5, site_id: "dev-site", local_date: "2026-11-17", identity_kind: "PERSON", identity_key: "P:B1", bamboohr_id: "B1",
    zk_emp_code: null, identity_snapshot: { kind: "PERSON", mapping_state: "VERIFIED", zk_emp_codes: ["9001"], mapping_ids: [1] },
    exception_type: "DEPARTURE_TIME_QUERY", status: "SUBMITTED", version: 2, allowed_actions: ["submit", "resolve"],
    justification_reason: "FORGOT_TO_RECORD", explanation: "Manager confirmed (synthetic)", declared_departure_local: "2026-11-17T18:00:00+05:30",
    declaration_source: "MANAGER_CONFIRMATION", evidence_reference: null, estimated_minutes: 570,
    estimate_basis: "First recorded fingerprint 08:30 → declared departure 18:00", outcome: null, decision_note: null, duration_verified: false,
    facts_snapshot: facts, opened_by_name: "A", opened_at: null, submitted_by_name: "A", submitted_at: null, resolved_by_name: null,
    resolved_at: null, reopened_by_name: null, reopened_at: null, reopen_reason: null, stale: false, reassess_reasons: [] };

  it("shows observed, declared and estimated values separately and reports a concurrent change", async () => {
    api.getReviewDay.mockResolvedValue({ case: CASE, history: [], can_manage: true, punches: [], current_facts: facts });
    api.resolveReview.mockRejectedValue(new ApiError(409, "conflict", { detail: { error: "This case was changed by another administrator — reload it" } }));
    const { AttendanceReviewDialog } = await import("@/components/AttendanceReviewDialog");
    renderPage(<AttendanceReviewDialog target={{ siteId: "dev-site", date: "2026-11-17", bamboohrId: "B1", label: "Verified Person" }} onClose={() => {}} />);
    expect(await screen.findByText("9h 00m")).toBeInTheDocument(); // Recorded Span (observed)
    expect(screen.getByText("9h 30m")).toBeInTheDocument(); // estimate, labelled separately
    expect(screen.getByText(/Estimated interval — reviewed declaration, not a confirmed duration/)).toBeInTheDocument();
    expect(screen.getByText(/Declared departure \(administrative declaration\)/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Outcome"), { target: { value: "JUSTIFIED" } });
    fireEvent.change(screen.getByLabelText(/Decision note/), { target: { value: "Reviewed with the team lead." } });
    fireEvent.click(screen.getByRole("button", { name: "Resolve case" }));
    await waitFor(() => expect(api.resolveReview).toHaveBeenCalledWith(5, { expected_version: 2, outcome: "JUSTIFIED", decision_note: "Reviewed with the team lead." }));
    expect(await screen.findByText(/changed by another administrator/)).toBeInTheDocument();
  });

  it("requires a source for a declared departure and a 10-character explanation", async () => {
    api.getReviewDay.mockResolvedValue({ case: { ...CASE, status: "OPEN", version: 1, allowed_actions: ["submit"] }, history: [],
      can_manage: true, punches: [], current_facts: facts });
    const { AttendanceReviewDialog } = await import("@/components/AttendanceReviewDialog");
    renderPage(<AttendanceReviewDialog target={{ siteId: "dev-site", date: "2026-11-17", bamboohrId: "B1", label: "P" }} onClose={() => {}} />);
    const submit = await screen.findByRole("button", { name: "Submit justification" });
    fireEvent.change(screen.getByLabelText("Justification"), { target: { value: "OTHER" } });
    fireEvent.change(screen.getByLabelText(/Explanation/), { target: { value: "short" } });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Explanation/), { target: { value: "A long enough explanation" } });
    fireEvent.change(screen.getByLabelText(/Declared departure/), { target: { value: "18:00" } });
    expect(submit).toBeDisabled(); // a declared departure needs its source
    expect(screen.getByText(/must not be earlier than the latest recorded fingerprint \(17:30\)/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Declaration source"), { target: { value: "TEAM_MEMBER_STATEMENT" } });
    expect(submit).toBeEnabled();
  });
});

describe("Overview — Earliest / Latest Recorded Fingerprint", () => {
  it("shows the times, ties and a single-day hint", async () => {
    setTestUrl("/?from=2026-11-17&to=2026-11-17");
    api.getOverview.mockResolvedValue({ site_id: "dev-site", date: "2026-11-17", time_zone: "Asia/Colombo", directory_available: true,
      kpis: { employees_with_activity: 1, total_events: 4, employees_needing_review: 0, single_punch_employees: 0, unmatched_codes: 0,
        feed_state: "FRESH", recorded_events: 6, verified_events: 4, unmapped_events: 1, conflict_events: 1 },
      review_breakdown: {}, last_successful_sync_at: null, latest_received_utc: null, agent_heartbeat_utc: null,
      extremes: { date: "2026-11-17", time_zone: "Asia/Colombo",
        earliest: { local_time: "2026-11-17T08:30:00+05:30", punch_time_utc: "x", tied: 2, entries: [
          { zk_emp_code: "9001", mapping_state: "VERIFIED", local_time: "2026-11-17T08:30:00+05:30", bamboohr_id: "B1", employee_name: "Verified Person", employee_number: "E-1", terminal: null },
          { zk_emp_code: "352", mapping_state: "UNMAPPED", local_time: "2026-11-17T08:30:00+05:30", bamboohr_id: null, employee_name: null, employee_number: null, terminal: null }] },
        latest: { local_time: "2026-11-17T17:45:00+05:30", punch_time_utc: "y", tied: 1, entries: [
          { zk_emp_code: "352", mapping_state: "UNMAPPED", local_time: "2026-11-17T17:45:00+05:30", bamboohr_id: null, employee_name: null, employee_number: null, terminal: null }] } } });
    api.getHourly.mockResolvedValue({ hours: [] });
    api.getTrend.mockResolvedValue({ days: [] });
    api.getRecent.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    const earliest = await screen.findByRole("link", { name: /Earliest Recorded Fingerprint/ });
    expect(earliest).toHaveTextContent("08:30");
    expect(earliest).toHaveTextContent("+1 tied");
    expect(earliest).toHaveAttribute("href", expect.stringContaining("view=events"));
    const latest = screen.getByRole("link", { name: /Latest Recorded Fingerprint/ });
    expect(latest).toHaveTextContent("ZKBioTime ID 352");
    expect(document.body.textContent).not.toMatch(/First Arrival|Last Departure/i);
  });
});

describe("Report export dialog", () => {
  it("maps each report to its endpoint and supported filters only", async () => {
    const { exportRequest, REPORTS } = await import("@/components/ReportExportDialog");
    const v = { siteId: "s", today: "2026-11-18", from: "2026-11-01", to: "2026-11-07", q: "Ann", emp: " 352 ", mapping: "unverified",
      dept: "Ops", term: "Main Door", flag: "SINGLE_PUNCH", review: "OPEN", detail: "both" };
    expect(exportRequest("daily", v)).toEqual({ path: "activity/daily", params: { site_id: "s", date_from: "2026-11-01", date_to: "2026-11-07",
      q: "Ann", emp_code: "352", mapping: "unverified", terminal: "Main Door", review_status: "OPEN", detail: "both" } });
    expect(exportRequest("overview", v)).toEqual({ path: "dashboard/overview", params: { site_id: "s", date: "2026-11-07" } });
    expect(exportRequest("verified", v).params.mapping).toBe("verified");
    expect(exportRequest("team", v).params).not.toHaveProperty("mapping");
    expect(REPORTS.daily.label).toBe("Daily Fingerprint Activity Summary");
  });

  it("blocks ranges over 92 days and is keyboard operable", async () => {
    const { ReportExportDialog } = await import("@/components/ReportExportDialog");
    renderPage(<ReportExportDialog context={{ report: "daily", siteId: "dev-site", today: "2026-11-18", from: "2026-11-12", to: "2026-11-18" }}
      onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Date range"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    expect(screen.getByText("The date range is limited to 92 days.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export to Excel/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-11-10" } });
    fireEvent.submit(screen.getByLabelText("Report type").closest("form")!);
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledWith("activity/daily",
      expect.objectContaining({ date_from: "2026-11-10", date_to: "2026-11-18", detail: "both" })));
  });
});

describe("v0.9 presentation rules", () => {
  it("DataView has no nested vertical scroller", async () => {
    const { DataView } = await import("@/components/DataView");
    window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as never;
    const { container } = render(<DataView caption="t" rows={[{ id: "a" }]} rowKey={(r) => r.id} card={() => null}
      columns={[{ key: "id", header: "ID", cell: (r: { id: string }) => r.id }]} />);
    const scroller = container.querySelector("[data-scroll-x]");
    if (scroller) {
      expect(scroller.className).not.toMatch(/max-h-|overflow-auto|overflow-y/);
      expect(scroller.className).toMatch(/overflow-x-auto/);
    }
  });

  it("charts use the onsite data palette with a non-colour cue per state", async () => {
    const { MAPPING_STATE } = await import("@/lib/format");
    expect([MAPPING_STATE.VERIFIED.bar, MAPPING_STATE.UNMAPPED.bar, MAPPING_STATE.CONFLICT.bar])
      .toEqual(["onsite-bar-verified", "onsite-bar-unmapped", "onsite-bar-conflict"]);
    const css = (await import("node:fs")).readFileSync("src/app/globals.css", "utf8");
    for (const c of ["#2c6e7a", "#c98a1e", "#6e1f2f", "repeating-linear-gradient", "radial-gradient", "onsite-seg-min"]) expect(css).toContain(c);
  });

  it("labels never describe a fingerprint as an exit, arrival or working time", async () => {
    const { SEQUENCE_LABEL, FINGERPRINT_DISCLAIMER } = await import("@/lib/format");
    const { FLAG_LABEL, FLAG_HELP } = await import("@/lib/flags");
    const { STATUS_LABEL, TYPE_LABEL } = await import("@/lib/reviews");
    const all = [...Object.values(SEQUENCE_LABEL), ...Object.values(FLAG_LABEL), ...Object.values(FLAG_HELP),
      ...Object.values(STATUS_LABEL), ...Object.values(TYPE_LABEL)].join(" | ").toLowerCase();
    for (const w of ["arrival", "check-out", "checkout", "clock out", "exit time", "last departure", "working hours", "time on site"]) {
      expect(all).not.toContain(w);
    }
    expect(SEQUENCE_LABEL.SINGLE).toBe("Single Recorded Fingerprint");
    expect(FINGERPRINT_DISCLAIMER).toMatch(/not a confirmed exit/);
  });
});
