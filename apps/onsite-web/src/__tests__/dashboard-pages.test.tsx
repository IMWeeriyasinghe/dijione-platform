import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } as { role: string; permissions: string[] } | null } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scope.value };
});

const api = vi.hoisted(() => ({
  getSitesInfo: vi.fn(), getOverview: vi.fn(), getHourly: vi.fn(), getTrend: vi.fn(), getRecent: vi.fn(),
  getToday: vi.fn(), getActivity: vi.fn(), getEmployees: vi.fn(), getEmployee: vi.fn(), getExceptions: vi.fn(),
  downloadExport: vi.fn(),
}));
vi.mock("@/lib/dashboard", async (orig) => {
  const actual = await orig<typeof import("@/lib/dashboard")>();
  return { ...actual, ...api };
});
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), requestSync: vi.fn(), getSyncRun: vi.fn(),
  getFreshness: vi.fn().mockResolvedValue({ source_configured: true, last_successful_sync_at: new Date().toISOString(), latest_run: null,
    sites: [{ site_id: "dev-site", feed_state: "FRESH", latest_received_utc: null, latest_punch_utc: null, agent_heartbeat_utc: null, agent_health: null }] }),
}));

const SITE = { site_id: "dev-site", name: "DEV Site (Colombo)", time_zone: "Asia/Colombo", today: "2026-11-01",
  first_activity_date: "2024-11-27", last_activity_date: "2026-10-21", terminals: ["Main Door"] };
const FLAGS0 = { SINGLE_PUNCH: 2, POSSIBLE_DUPLICATE_TAP: 1, UNMATCHED_CODE: 1, AMBIGUOUS_CODE: 0, INACTIVE_EMPLOYEE_ACTIVITY: 0,
  BEFORE_HIRE_ACTIVITY: 0, TZ_INCONSISTENT: 0, HIGH_PUNCH_COUNT: 0 };
const DAY = { local_date: "2026-10-13", emp_code: "0107", zk_emp_codes: ["0107"], bamboohr_id: "7", employee_number: "E-7",
  mapping_status: "MAPPED", employee_name: "Ishara G", department: "Bench",
  first_activity_local: "2026-10-13T08:37:00+05:30", latest_activity_local: "2026-10-13T08:37:20+05:30",
  punch_count: 2, span_minutes: 0, terminal_names: ["Main Door"], identity_class: "MATCHED_ACTIVE", flags: ["POSSIBLE_DUPLICATE_TAP"] };

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  scope.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } };
  api.getSitesInfo.mockResolvedValue([SITE]);
  api.getOverview.mockResolvedValue({ site_id: "dev-site", date: "2026-11-01", time_zone: "Asia/Colombo", directory_available: true,
    kpis: { employees_with_activity: 4, total_events: 6, employees_needing_review: 3, single_punch_employees: 2, unmatched_codes: 1, feed_state: "STALE" },
    review_breakdown: FLAGS0, last_successful_sync_at: "2026-10-21T23:42:48Z", latest_received_utc: null, agent_heartbeat_utc: null });
  api.getHourly.mockResolvedValue({ hours: Array.from({ length: 24 }, (_, h) => ({ hour: h, events: h === 8 ? 5 : 0, employees: 0 })) });
  api.getTrend.mockResolvedValue({ days: [{ date: "2026-10-31", events: 3, employees: 2 }, { date: "2026-11-01", events: 6, employees: 4 }] });
  api.getRecent.mockResolvedValue({ total: 1, page: 1, page_size: 12, directory_available: true,
    items: [{ emp_code: "101", employee_name: "Nimal P", department: "Bench", identity_class: "MATCHED_ACTIVE", local_time: "2026-10-21T15:20:26+05:30",
      local_date: "2026-10-21", terminal: "Main Door", area: null, punch_state_raw: "255", tz_consistent: true }] });
});

describe("Overview", () => {
  it("renders KPIs, charts, breakdown and recent activity from the API", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByText("Employees with activity")).toBeInTheDocument();
    expect(screen.getByText("Activity events")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /Activity events by hour, Today · Sun 1 Nov, DEV Site/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /08:00–08:59 \(Asia\/Colombo\): 5 events/ })).toBeInTheDocument();
    expect(screen.getByText("Possible duplicate tap")).toBeInTheDocument();
    expect(await screen.findByText("Nimal P")).toBeInTheDocument();
    expect(screen.getAllByText("Feed stale").length).toBeGreaterThan(0);
    expect(api.getOverview).toHaveBeenCalledWith({ site_id: "dev-site", date: "2026-11-01" });
  });

  it("drills into a day from the trend chart and re-queries", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /Sat 31 Oct 2026: 3 events/ }));
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledWith({ site_id: "dev-site", date: "2026-10-31" }));
  });

  it("shows Sync now only to admins", async () => {
    const { default: Page } = await import("@/app/page");
    const { unmount } = renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(screen.queryByRole("button", { name: /sync now/i })).not.toBeInTheDocument();
    unmount();
    scope.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read", "onsite.health.read", "onsite.identity.read", "onsite.sites.manage", "onsite.sync.request"] } };
    renderPage(<Page />);
    expect(await screen.findByRole("button", { name: /sync now/i })).toBeInTheDocument();
  });

  it("requires an enabled site", async () => {
    api.getSitesInfo.mockResolvedValue([]);
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByText("No enabled sites")).toBeInTheDocument();
    expect(api.getOverview).not.toHaveBeenCalled();
  });

  it("shows an error state when the API fails", async () => {
    api.getOverview.mockRejectedValue(new Error("boom"));
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByRole("button", { name: /retry|try again/i })).toBeInTheDocument();
  });

  it("uses a responsive KPI grid", async () => {
    const { default: Page } = await import("@/app/page");
    const { container } = renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(container.querySelector(".grid.grid-cols-2.sm\\:grid-cols-3")).not.toBeNull();
  });
});

describe("Today", () => {
  it("renders rows and applies filters", async () => {
    api.getToday.mockResolvedValue({ total: 1, page: 1, page_size: 50, date: "2026-11-01", departments: ["Bench"], directory_available: true, items: [DAY] });
    const { default: Page } = await import("@/app/today/page");
    renderPage(<Page />);
    expect(await screen.findByText("Ishara G")).toBeInTheDocument();
    expect(screen.getAllByText("08:37").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Needs review" }));
    await waitFor(() => expect(api.getToday).toHaveBeenLastCalledWith(expect.objectContaining({ review: "needs_review", page: 1 })));
  });

  it("shows the empty state", async () => {
    api.getToday.mockResolvedValue({ total: 0, page: 1, page_size: 50, date: "2026-11-01", departments: [], directory_available: true, items: [] });
    const { default: Page } = await import("@/app/today/page");
    renderPage(<Page />);
    expect(await screen.findByText("No activity recorded yet today")).toBeInTheDocument();
    expect(screen.getByText(/This is not an absence record/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Go to latest activity day/ }));
    await waitFor(() => expect(api.getToday).toHaveBeenLastCalledWith(expect.objectContaining({ date: "2026-10-21" })));
  });
});

describe("Exceptions", () => {
  it("shows counts and filters by flag", async () => {
    api.getExceptions.mockResolvedValue({ total: 1, page: 1, page_size: 25, directory_available: true, counts: FLAGS0,
      items: [{ ...DAY, reasons: [{ flag: "POSSIBLE_DUPLICATE_TAP", reason: "Two activities were recorded within 60 seconds of each other." }] }] });
    const { default: Page } = await import("@/app/exceptions/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /Show details for Ishara G/ }));
    expect(await screen.findByText("Possible duplicate tap:")).toBeInTheDocument();
    expect(screen.getAllByText(/within 60 seconds/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /View supporting events/ })).toHaveAttribute("href", expect.stringContaining("emp=0107"));
    fireEvent.click(screen.getByRole("button", { name: /^Single activity\s*2/ }));
    await waitFor(() => expect(api.getExceptions).toHaveBeenLastCalledWith(expect.objectContaining({ flag: "SINGLE_PUNCH" })));
  });
});

describe("Employees", () => {
  it("opens the employee detail drawer", async () => {
    api.getEmployees.mockResolvedValue({ total: 1, page: 1, page_size: 50, date_from: "x", date_to: "y", departments: [], directory_available: true,
      items: [{ emp_code: "0107", zk_emp_codes: ["0107"], bamboohr_id: "7", employee_number: "E-7", mapping_status: "MAPPED",
        employee_name: "Ishara G", department: "Bench", employment_status: "Active", identity_class: "MATCHED_ACTIVE", in_directory: true, events: 2, activity_days: 1, review_flags: 1, last_activity_local: "2026-10-13T08:37:20+05:30" }] });
    api.getEmployee.mockResolvedValue({ profile: { emp_code: "0107", zk_emp_codes: ["0107"], bamboohr_id: "7", employee_number: "E-7",
      mapping_status: "MAPPED", employee_name: "Ishara G", department: "Bench", employment_status: "Active",
      identity_class: "MATCHED_ACTIVE", job_title: "Support Engineer", match_count: 1 }, summary: { activity_days: 1, events: 2, review_flags: 1 },
      days: [DAY], events: [], directory_available: true });
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByText("Ishara G"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByText(/Support Engineer/)).toBeInTheDocument();
    // The profile is addressed by the verified BHR Employee ID, never by the ZKBioTime ID.
    expect(api.getEmployee).toHaveBeenCalledWith("7", expect.anything());
    expect(screen.getByText(/BHR Employee ID 7/)).toBeInTheDocument();
    expect(screen.getByText(/BambooHR Employee Number E-7/)).toBeInTheDocument();
  });
});

describe("Activity", () => {
  it("renders raw device state verbatim", async () => {
    api.getActivity.mockResolvedValue({ total: 1, page: 1, page_size: 50, directory_available: true,
      items: [{ emp_code: "101", bamboohr_id: "1", mapping_status: "MAPPED", employee_name: "Nimal P", department: null,
        identity_class: "MATCHED_ACTIVE", local_time: "2026-10-13T08:39:00+05:30",
        local_date: "2026-10-13", terminal: "Main Door", area: null, punch_state_raw: "255", tz_consistent: true }] });
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    expect(await screen.findByText("255")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument(); // Mapping Status badge
    expect(screen.queryByText(/Unmatched|Unmapped/)).not.toBeInTheDocument(); // viewers never see unmapped IDs
    expect(screen.queryByText("IN")).not.toBeInTheDocument();
    expect(screen.queryByText("OUT")).not.toBeInTheDocument();
  });
});

describe("Excel export", () => {
  const TODAY = { total: 1, page: 1, page_size: 50, date: "2026-11-01", departments: ["Finance"], directory_available: true, items: [DAY] };

  it("exports exactly the filters on screen (no paging/sort)", async () => {
    api.getSitesInfo.mockResolvedValue([{ ...SITE, departments: ["Finance", "Bench"] }]);
    api.getToday.mockResolvedValue(TODAY);
    api.downloadExport.mockResolvedValue(undefined);
    const { default: Page } = await import("@/app/today/page");
    renderPage(<Page />);
    await screen.findByText("Ishara G");
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "Finance" } });
    fireEvent.change(screen.getByLabelText("ZKBioTime ID"), { target: { value: "0107" } });
    // search input is debounced: wait until the filter reaches the query
    await waitFor(() => expect(api.getToday).toHaveBeenLastCalledWith(expect.objectContaining({ emp_code: "0107" })));
    fireEvent.click(screen.getByRole("button", { name: /export to excel/i }));
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledTimes(1));
    const [path, params] = api.downloadExport.mock.calls[0];
    expect(path).toBe("today");
    expect(params).toMatchObject({ site_id: "dev-site", date: "2026-11-01", department: "Finance", emp_code: "0107" });
    expect(params).not.toHaveProperty("page");
    expect(params).not.toHaveProperty("sort");
  });

  it("ignores the current page: page 2 exports the same filtered dataset, filters still change it", async () => {
    api.getSitesInfo.mockResolvedValue([{ ...SITE, departments: ["Finance", "Bench"] }]);
    api.getToday.mockImplementation(async (p: { page: number }) => ({ ...TODAY, total: 137, page: p.page }));
    api.downloadExport.mockResolvedValue(undefined);
    const { default: Page } = await import("@/app/today/page");
    renderPage(<Page />);
    await screen.findByText("Ishara G");
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "Finance" } });
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    await waitFor(() => expect(api.getToday).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, department: "Finance" })));
    fireEvent.click(screen.getByRole("button", { name: /export to excel/i }));
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledTimes(1));
    const onPage2 = api.downloadExport.mock.calls[0][1];
    expect(onPage2).toEqual({ site_id: "dev-site", date: "2026-11-01", department: "Finance" });
    for (const k of ["page", "page_size", "sort"]) expect(onPage2).not.toHaveProperty(k);
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "Bench" } });
    fireEvent.click(screen.getByRole("button", { name: /export to excel/i }));
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledTimes(2));
    expect(api.downloadExport.mock.calls[1][1]).toMatchObject({ department: "Bench" });
  });

  it("shows the server's message when an export is too large", async () => {
    api.getActivity.mockResolvedValue({ total: 0, page: 1, page_size: 50, directory_available: true, items: [] });
    api.downloadExport.mockRejectedValue(new Error("This export would contain 60,000 rows, above the limit of 50,000. Narrow the date range or add filters and try again."));
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /export to excel/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Narrow the date range/);
  });

  it("is offered on every operational page", async () => {
    api.getToday.mockResolvedValue(TODAY);
    api.getActivity.mockResolvedValue({ total: 0, page: 1, page_size: 50, directory_available: true, items: [] });
    api.getEmployees.mockResolvedValue({ total: 0, page: 1, page_size: 50, date_from: "x", date_to: "y", departments: [], directory_available: true, items: [] });
    api.getExceptions.mockResolvedValue({ total: 0, page: 1, page_size: 25, directory_available: true, counts: FLAGS0, items: [] });
    for (const mod of ["today", "activity", "employees", "exceptions"]) {
      const { default: Page } = await import(`@/app/${mod}/page`);
      const { unmount } = renderPage(<Page />);
      expect(await screen.findByRole("button", { name: /export to excel/i })).toBeInTheDocument();
      unmount();
    }
    const { default: Overview } = await import("@/app/page");
    renderPage(<Overview />);
    expect(await screen.findByRole("button", { name: /export day summary/i })).toBeInTheDocument();
  });
});
