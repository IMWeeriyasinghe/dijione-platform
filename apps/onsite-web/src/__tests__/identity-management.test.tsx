import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@dijione/auth-client";
import { setTestUrl } from "@/test-navigation";

const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_ADMIN", permissions: [] as string[] } } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scope.value };
});

const dash = vi.hoisted(() => ({ getSitesInfo: vi.fn() }));
vi.mock("@/lib/dashboard", async (orig) => ({ ...(await orig<typeof import("@/lib/dashboard")>()), ...dash }));

const id = vi.hoisted(() => ({
  getReadiness: vi.fn(), getUnmapped: vi.fn(), getCodeDetail: vi.fn(), getEvidence: vi.fn(), searchDirectory: vi.fn(),
  getMappings: vi.fn(), getMapping: vi.fn(), getConflicts: vi.fn(), createMapping: vi.fn(), closeMapping: vi.fn(),
  correctMapping: vi.fn(), reassignCode: vi.fn(), rejectAssociation: vi.fn(), withdrawRejection: vi.fn(),
  importMappings: vi.fn(), downloadIdentityList: vi.fn(), getCoverage: vi.fn(),
}));
vi.mock("@/lib/identity", async (orig) => ({ ...(await orig<typeof import("@/lib/identity")>()), ...id }));

const READ = ["onsite.dashboard.read", "onsite.attendance.read", "onsite.identity.read"];
const MANAGE = [...READ, "onsite.identity.manage"];
const SITE = { site_id: "colombo", name: "Colombo Office", time_zone: "Asia/Colombo", today: "2026-11-14",
  first_activity_date: null, last_activity_date: null, terminals: [] };
const UNMAPPED = {
  site_id: "colombo", zk_emp_code: "352", first_seen: "2026-11-01", last_seen: "2026-11-13", event_count: 20, activity_days: 10,
  unmapped_events: 20, unmapped_days: 10, first_unmapped: "2026-11-01", last_unmapped: "2026-11-13", mapped_today: false,
  mapping_count: 0, rejections: [],
  hint_employee_number_matches: [{ bamboohr_id: "900", display_name: "Number Twin", employment_status: "Active", basis: "EMPLOYEE_NUMBER_EQUALS_ID_UNVERIFIED" }],
};
const TOM = { bamboohr_id: "1234", display_name: "Tom Example", employee_number: "352", department: "Bench", job_title: null,
  employment_status: "Active", hire_date: "2026-11-01", termination_date: null, has_photo: false, active_codes: [] };
const MAPPING = { id: 7, site_id: "colombo", zk_emp_code: "131", bamboohr_id: "1", employee_name: "A", employee_number: "131",
  employee_in_directory: true, valid_from: "2025-01-10", valid_to: null, status: "VERIFIED", evidence: "Enrolment sheet", source: "MANUAL",
  verified_by_user_id: 1, verified_at: "2026-11-14T00:00:00Z", closed_reason: null, superseded_reason: null, superseded_by_id: null };

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function openPage(tab?: string) {
  setTestUrl(tab ? `/admin/identity?tab=${tab}` : "/admin/identity");
  const { default: Page } = await import("@/app/admin/identity/page");
  return renderPage(<Page />);
}

beforeEach(() => {
  Object.values(id).forEach((f) => f.mockReset());
  dash.getSitesInfo.mockReset().mockResolvedValue([SITE]);
  scope.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: MANAGE } };
  id.getReadiness.mockResolvedValue({ site_id: "colombo", window_days: 30, date_from: "2026-10-16", date_to: "2026-11-14",
    total_punches: 100, identified_punches: 80, identified_punch_pct: 80, identified_employees: 12, active_codes: 15,
    unmapped_codes: 3, unmapped_punches: 20, high_volume_outstanding_codes: [{ zk_emp_code: "3", unmapped_events: 15, disposition: "undispositioned" }],
    unresolved_conflicts: { conflict_days: 0, overlapping_mappings: 0, ambiguous_reassignment_days: 1 }, verified_mappings: 12,
    mappings_without_evidence: 0, import_batches: [], directory_available: true, decision: "NOT_AUTOMATIC" });
  id.getUnmapped.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [UNMAPPED] });
  id.getMappings.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [MAPPING] });
  id.searchDirectory.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [TOM] });
  id.getEvidence.mockResolvedValue({ warnings: [] });
  id.getCoverage.mockImplementation(async (p: { date_from: string; date_to: string }) => coverage(p));
});

function coverage(p: { date_from: string; date_to: string }) {
  const narrow = p.date_from === p.date_to;
  return {
    site_id: "colombo", date_from: p.date_from, date_to: p.date_to,
    ids: { observed: narrow ? 2 : 5, verified: 2, fully_verified: 1, partly_verified: 1, unmapped: narrow ? 0 : 3 },
    punches: { total: 100, verified: 60, unmapped: 40, coverage_pct: 60 },
    verified_team_members: 1,
    unresolved_conflicts: { total: 1, conflict_days: 0, ambiguous_reassignment_days: 1, overlapping_mappings: 0 },
    trend: [{ date: p.date_to, verified_punches: 60, unmapped_punches: 40 }],
    top_unmapped: [
      { zk_emp_code: "352", unmapped_punches: 30, unmapped_days: 5, first_unmapped: "2026-11-01", last_unmapped: "2026-11-13", mapped_now: false },
      { zk_emp_code: "3", unmapped_punches: 10, unmapped_days: 2, first_unmapped: "2026-11-02", last_unmapped: "2026-11-10", mapped_now: true },
    ],
    ingestion: { feed_state: "FRESH", latest_received_utc: "2026-11-14T06:00:00Z", last_successful_sync_at: "2026-11-14T06:01:00Z" },
    directory_available: true,
  };
}

describe("Identity Management", () => {
  it("is admin-only and keeps the /admin/identity route", async () => {
    scope.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.dashboard.read"] } };
    await openPage();
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(id.getReadiness).not.toHaveBeenCalled();
  });

  it("shows readiness figures without a pass/fail verdict", async () => {
    await openPage("readiness");
    expect(await screen.findByText("Identified punches")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText(/approved separately by the owner/)).toBeInTheDocument();
    expect(screen.getByText("undispositioned")).toBeInTheDocument();
  });

  it("lists unmapped IDs with a labelled hint that is never pre-selected", async () => {
    await openPage("unmapped");
    expect(await screen.findByText("352")).toBeInTheDocument();
    expect(screen.getByText("Unverified: Number Twin")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Map…" }));
    const dialog = await screen.findByRole("heading", { name: /Map ZKBioTime ID/ });
    const modal = dialog.closest("div")!.parentElement!;
    // Nothing selected and no start date assumed: confirm is disabled.
    expect(within(modal).getByLabelText(/Owned from/)).toHaveValue("");
    expect(within(modal).getByRole("button", { name: "Confirm mapping" })).toBeDisabled();
    expect(id.searchDirectory).not.toHaveBeenCalled(); // no search until the admin types
  });

  it("requires a typed search, explicit dates, evidence and every warning acknowledged before mapping", async () => {
    id.getEvidence.mockResolvedValue({ warnings: [{ code: "PRIOR_UNMAPPED_ACTIVITY", message: "4 earlier punches stay unmapped.", events: 4 }] });
    id.createMapping.mockResolvedValue({ ...MAPPING, zk_emp_code: "352", bamboohr_id: "1234" });
    await openPage("unmapped");
    fireEvent.click(await screen.findByRole("button", { name: "Map…" }));
    fireEvent.change(screen.getByLabelText("Search the BambooHR Workforce Directory"), { target: { value: "tom" } });
    await waitFor(() => expect(id.searchDirectory).toHaveBeenCalledWith("tom"), { timeout: 2000 });
    fireEvent.click(await screen.findByRole("radio"));
    fireEvent.change(screen.getByLabelText(/Owned from/), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText(/Verification evidence/), { target: { value: "IT enrolment sheet signed by HR" } });
    const box = await screen.findByRole("checkbox", { name: /Earlier punches stay unmapped/ });
    expect(screen.getByTestId("confirm-sentence")).toHaveTextContent(
      "Map ZKBioTime ID 352 to Tom Example (BHR Employee ID 1234, EMP Number 352) from 2026-11-01 (open-ended) — 4 earlier punch(es) stay unmapped.");
    const confirm = screen.getByRole("button", { name: "Confirm mapping" });
    expect(confirm).toBeDisabled();
    fireEvent.click(box);
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(id.createMapping).toHaveBeenCalledWith({ site_id: "colombo", zk_emp_code: "352", bamboohr_id: "1234",
      valid_from: "2026-11-01", valid_to: null, evidence: "IT enrolment sheet signed by HR", acknowledged_warnings: ["PRIOR_UNMAPPED_ACTIVITY"] }));
  });

  it("shows a server conflict instead of saving", async () => {
    id.createMapping.mockRejectedValue(new ApiError(409, JSON.stringify({ error: "OVERLAPPING_MAPPING",
      message: "This ZKBioTime ID already has a verified owner in that period.", conflicts: [MAPPING] })));
    await openPage("unmapped");
    fireEvent.click(await screen.findByRole("button", { name: "Map…" }));
    fireEvent.change(screen.getByLabelText("Search the BambooHR Workforce Directory"), { target: { value: "tom" } });
    fireEvent.click(await screen.findByRole("radio", {}, { timeout: 2000 }));
    fireEvent.change(screen.getByLabelText(/Owned from/), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText(/Verification evidence/), { target: { value: "IT enrolment sheet signed by HR" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm mapping" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(await screen.findByText(/already has a verified owner/)).toBeInTheDocument();
  });

  it("offers lifecycle actions only to managers", async () => {
    await openPage("mappings");
    expect(await screen.findByRole("button", { name: "Reassign…" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End…" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correct…" })).toBeInTheDocument();
  });

  it("is read-only without onsite.identity.manage", async () => {
    scope.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: READ } };
    await openPage("mappings");
    expect((await screen.findAllByText("131")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "History" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reassign…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Map ZKBioTime ID" })).not.toBeInTheDocument();
    expect(screen.getByText(/Read-only/)).toBeInTheDocument();
  });

  it("asks for explicit same-day handling when the reassignment day has punches", async () => {
    id.reassignCode
      .mockRejectedValueOnce(new ApiError(422, JSON.stringify({ error: "REASSIGNMENT_DAY_HAS_ACTIVITY", events_on_day: 2,
        options: ["leave_unmapped", "attribute_to_new", "attribute_to_previous"], message: "2 punch(es) cannot be split" })))
      .mockResolvedValueOnce({ previous: MAPPING, new: MAPPING, same_day_handling: "leave_unmapped", unmapped_day: "2026-06-01" });
    await openPage("mappings");
    fireEvent.click(await screen.findByRole("button", { name: "Reassign…" }));
    fireEvent.change(screen.getByLabelText(/New owner from/), { target: { value: "2026-06-01" } });
    fireEvent.change(screen.getByLabelText("Search the BambooHR Workforce Directory"), { target: { value: "tom" } });
    fireEvent.click(await screen.findByRole("radio", {}, { timeout: 2000 }));
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: "Code reissued by IT to Tom" } });
    fireEvent.change(screen.getByLabelText(/Verification evidence for the new owner/), { target: { value: "IT enrolment sheet signed by HR" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and reassign" }));
    expect(await screen.findByText(/cannot be split automatically/)).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm reassignment" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /Leave that day unmapped/ }));
    fireEvent.click(confirm);
    await waitFor(() => expect(id.reassignCode).toHaveBeenLastCalledWith("131", expect.objectContaining({ same_day_handling: "leave_unmapped",
      effective_from: "2026-06-01" })));
  });

  it("import requires a dry run and blocks apply while errors remain", async () => {
    id.importMappings.mockResolvedValueOnce({ dry_run: true, can_apply: false, dry_run_token: null,
      summary: { rows: 1, rows_with_errors: 1, rows_with_warnings: 0, warning_codes: [] },
      rows: [{ line: 2, zk_emp_code: "352", bamboohr_id: "1234", errors: ["EVIDENCE_REQUIRED"], warnings: [] }] });
    await openPage("import");
    const input = await screen.findByLabelText("Mappings CSV file");
    fireEvent.change(input, { target: { files: [new File(["x"], "m.csv", { type: "text/csv" })] } });
    fireEvent.click(screen.getByRole("button", { name: /Dry run/ }));
    expect(await screen.findByText("EVIDENCE_REQUIRED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Apply/ })).not.toBeInTheDocument();
    expect(id.importMappings).toHaveBeenCalledWith(expect.any(File), { dryRun: true });
  });
});

describe("Identity Management — fail-closed confirmation", () => {
  it("keeps Confirm disabled for an incomplete date and when the evidence check fails", async () => {
    await openPage("unmapped");
    fireEvent.click(await screen.findByRole("button", { name: "Map…" }));
    fireEvent.change(screen.getByLabelText("Search the BambooHR Workforce Directory"), { target: { value: "tom" } });
    fireEvent.click(await screen.findByRole("radio", {}, { timeout: 2000 }));
    fireEvent.change(screen.getByLabelText(/Verification evidence/), { target: { value: "IT enrolment sheet signed by HR" } });
    fireEvent.change(screen.getByLabelText(/Owned from/), { target: { value: "2026-02-31" } }); // not a real date (sanitised to "")
    expect(screen.getByRole("button", { name: "Confirm mapping" })).toBeDisabled();
    expect(screen.queryByTestId("confirm-sentence")).not.toBeInTheDocument();
    expect(id.getEvidence).not.toHaveBeenCalled();
    id.getEvidence.mockRejectedValue(new ApiError(503, JSON.stringify({ error: "DIRECTORY_UNAVAILABLE", message: "The Workforce Directory is unavailable." })));
    fireEvent.change(screen.getByLabelText(/Owned from/), { target: { value: "2026-11-01" } });
    expect(await screen.findByText(/Workforce Directory is unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm mapping" })).toBeDisabled();
    expect(screen.queryByText(/No evidence warnings/)).not.toBeInTheDocument();
  });
});

describe("isIsoDate", () => {
  it("accepts only complete, real calendar dates", async () => {
    const { isIsoDate } = await import("@/components/identity/dialogs");
    expect(isIsoDate("2026-11-01")).toBe(true);
    for (const bad of ["", "2026-02-31", "101420-02-06", "2026-1-1", "01/11/2026"]) expect(isIsoDate(bad)).toBe(false);
  });
});

describe("Identity Management overview", () => {
  it("is the default tab and shows real coverage figures for the last 30 site days", async () => {
    await openPage();
    expect(await screen.findByText("Verified coverage")).toBeInTheDocument();
    expect(id.getCoverage).toHaveBeenCalledWith({ site_id: "colombo", date_from: "2026-10-16", date_to: "2026-11-14" });
    expect(screen.getByText("60%")).toBeInTheDocument();
    // biometric IDs are never presented as people
    expect(screen.getByText("ZKBioTime IDs observed")).toBeInTheDocument();
    expect(screen.getByText("Biometric IDs, not people")).toBeInTheDocument();
    expect(screen.getByText("Verified team members")).toBeInTheDocument();
    expect(screen.getByText(/stored safely; the remaining step is identity verification and mapping by the administration team/)).toBeInTheDocument();
  });

  it("separates a feed problem from the mapping backlog", async () => {
    id.getCoverage.mockImplementation(async (p: { date_from: string; date_to: string }) => ({ ...coverage(p), ingestion: { feed_state: "STALE", latest_received_utc: null, last_successful_sync_at: null } }));
    await openPage();
    expect(await screen.findByText(/feed\/synchronisation matter, separate from the mapping backlog/)).toBeInTheDocument();
  });

  it("refetches every figure when the period changes", async () => {
    await openPage();
    await screen.findByText("Verified coverage");
    fireEvent.click(screen.getByRole("button", { name: "Today" }));
    await waitFor(() => expect(id.getCoverage).toHaveBeenLastCalledWith({ site_id: "colombo", date_from: "2026-11-14", date_to: "2026-11-14" }));
  });

  it("ranks unmapped IDs; selecting one filters the mapping workflow and Map opens the dialog", async () => {
    await openPage();
    const list = await screen.findByRole("list", { name: /most unmapped punches/ });
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("352");
    fireEvent.click(within(items[0]).getByRole("button", { name: "Map…" }));
    expect(await screen.findByRole("heading", { name: /Map ZKBioTime ID/ })).toBeInTheDocument();
  });

  it("investigating an ID opens the Unmapped tab filtered to it", async () => {
    await openPage();
    fireEvent.click(await screen.findByRole("button", { name: "352" }));
    await waitFor(() => expect(id.getUnmapped).toHaveBeenCalledWith(expect.objectContaining({ q: "352" })));
  });

  it("hides Map actions for read-only identity users", async () => {
    scope.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: READ } };
    await openPage();
    await screen.findByRole("list", { name: /most unmapped punches/ });
    expect(screen.queryByRole("button", { name: "Map…" })).not.toBeInTheDocument();
  });
});
