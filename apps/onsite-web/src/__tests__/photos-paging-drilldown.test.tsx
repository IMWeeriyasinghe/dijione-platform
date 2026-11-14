import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getTestUrl, setTestUrl } from "@/test-navigation";

const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } } }));
vi.mock("@/lib/onsite-scope", async (orig) => ({ ...(await orig<typeof import("@/lib/onsite-scope")>()), useOnsiteScope: () => scope.value }));
const api = vi.hoisted(() => ({
  getSitesInfo: vi.fn(), getOverview: vi.fn(), getHourly: vi.fn(), getTrend: vi.fn(), getRecent: vi.fn(),
  getToday: vi.fn(), getActivity: vi.fn(), getEmployees: vi.fn(), getEmployee: vi.fn(), getExceptions: vi.fn(),
  downloadExport: vi.fn(), getEmployeePhoto: vi.fn(),
}));
vi.mock("@/lib/dashboard", async (orig) => ({ ...(await orig<typeof import("@/lib/dashboard")>()), ...api }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), requestSync: vi.fn(), getSyncRun: vi.fn(),
  getFreshness: vi.fn().mockResolvedValue({ source_configured: true, last_successful_sync_at: new Date().toISOString(), latest_run: null, sites: [] }),
}));

const SITE = { site_id: "colombo", name: "Colombo Office", time_zone: "Asia/Colombo", today: "2026-11-04",
  first_activity_date: "2024-11-27", last_activity_date: "2026-11-03", terminals: ["Main Door"], departments: ["Finance"] };
const row = (code: string, photo: boolean) => ({ emp_code: code, zk_emp_codes: [code], bamboohr_id: `B${code}`, mapping_status: "MAPPED", employee_name: `Person ${code}`, department: "Finance", employment_status: "Active",
  identity_class: "MATCHED_ACTIVE", in_directory: true, has_photo: photo, events: 3, activity_days: 2, review_flags: 0, last_activity_local: null });
const EMP = (total: number, items: ReturnType<typeof row>[]) => ({ total, page: 1, page_size: 10, date_from: "x", date_to: "y", departments: [],
  directory_available: true, items, summary: { employees: total, with_activity: total, active: total, inactive: 0, not_in_directory: 0, needing_review: 0, matched: total } });
const EVENT = (code: string, time: string) => ({ emp_code: code, bamboohr_id: `B${code}`, mapping_status: "MAPPED", employee_name: `Person ${code}`, department: "Finance", identity_class: "MATCHED_ACTIVE",
  has_photo: true, local_date: "2026-11-03", local_time: `2026-11-03T${time}:00+05:30`, terminal: "Main Door", area: null, punch_state_raw: "255",
  tz_consistent: true, review_flags: ["POSSIBLE_DUPLICATE_TAP"] });

let client: QueryClient;
function renderPage(ui: React.ReactElement) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  window.localStorage.clear();
  api.getSitesInfo.mockResolvedValue([SITE]);
  api.getEmployeePhoto.mockImplementation(async (bhr: string) => (bhr === "B101" ? `blob:photo-${bhr}` : null));
  api.getOverview.mockResolvedValue({ site_id: "colombo", date: "x", time_zone: "Asia/Colombo", directory_available: true,
    kpis: { employees_with_activity: 2, total_events: 3, employees_needing_review: 0, single_punch_employees: 0, unmatched_codes: 0, feed_state: "FRESH" },
    review_breakdown: {}, last_successful_sync_at: null, latest_received_utc: null, agent_heartbeat_utc: null });
  api.getHourly.mockResolvedValue({ hours: Array.from({ length: 24 }, (_, h) => ({ hour: h, events: h === 11 ? 3 : h === 9 ? 1 : 0, employees: h === 11 ? 2 : h === 9 ? 1 : 0 })) });
  api.getTrend.mockResolvedValue({ days: [{ date: "2026-11-02", events: 4, employees: 2 }, { date: "2026-11-03", events: 3, employees: 2 }] });
  api.getRecent.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
});
afterEach(() => vi.useRealTimers());

describe("Profile photos", () => {
  it("shows real photos where available and initials otherwise, without delaying the list", async () => {
    api.getEmployees.mockResolvedValue(EMP(2, [row("101", true), row("102", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    expect(await screen.findByText("Person 102")).toBeInTheDocument(); // rendered before any photo resolves
    await waitFor(() => expect(document.querySelector('img[src="blob:photo-B101"]')).not.toBeNull());
    expect(api.getEmployeePhoto).toHaveBeenCalledTimes(1);              // never requested for has_photo=false
    expect(api.getEmployeePhoto).toHaveBeenCalledWith("B101"); // photos are fetched only by verified BHR Employee ID
    expect(screen.getAllByText("P1").length).toBeGreaterThan(0);        // initials stay underneath as the fallback
  });

  it("falls back to initials when the photo is missing or fails to load", async () => {
    api.getEmployeePhoto.mockResolvedValue(null);
    api.getEmployees.mockResolvedValue(EMP(1, [row("101", true)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await screen.findByText("Person 101");
    await waitFor(() => expect(api.getEmployeePhoto).toHaveBeenCalled());
    expect(document.querySelector("img")).toBeNull();
    api.getEmployeePhoto.mockResolvedValue("blob:broken");
    client.clear();
  });

  it("does not download photos again on the 30-second refresh", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.getEmployees.mockResolvedValue(EMP(1, [row("101", true)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await waitFor(() => expect(api.getEmployeePhoto).toHaveBeenCalledTimes(1));
    const before = api.getEmployees.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(31_000); });
    await waitFor(() => expect(api.getEmployees.mock.calls.length).toBeGreaterThan(before)); // data refreshed
    expect(api.getEmployeePhoto).toHaveBeenCalledTimes(1);                                   // photo did not
  });
});

describe("Server-side pagination", () => {
  it("defaults to 10 per page and shows a range label", async () => {
    api.getEmployees.mockResolvedValue(EMP(506, [row("101", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    expect(await screen.findByText("1–10 of 506 team members")).toBeInTheDocument();
    expect(api.getEmployees).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 10 }));
    expect(screen.getByLabelText("Rows per page")).toHaveValue("10");
    expect([...screen.getByLabelText("Rows per page").querySelectorAll("option")].map((o) => o.textContent)).toEqual(["10", "20", "50", "100"]);
  });

  it("changes page size, returns to page 1 and remembers the choice per view", async () => {
    setTestUrl("/employees?page=3");
    api.getEmployees.mockResolvedValue(EMP(506, [row("101", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await screen.findByText("Person 101");
    expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, page_size: 10 }));
    fireEvent.change(screen.getByLabelText("Rows per page"), { target: { value: "50" } });
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 50 })));
    expect(window.localStorage.getItem("onsite.pageSize.employees")).toBe("50");
    expect(window.localStorage.getItem("onsite.pageSize.today")).toBeNull();
  });

  it("navigates next/previous and keeps the page through background refreshes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.getEmployees.mockResolvedValue(EMP(35, [row("101", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await screen.findByText("Person 101");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
    await act(async () => { await vi.advanceTimersByTimeAsync(31_000); });
    expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    expect(getTestUrl().searchParams.get("page")).toBe("2");
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 })));
  });

  it("resets to page 1 on filter changes and clamps a page that no longer exists", async () => {
    setTestUrl("/employees?page=4");
    api.getEmployees.mockResolvedValue(EMP(12, [row("101", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await waitFor(() => expect(getTestUrl().searchParams.get("page")).toBe("2")); // 12 rows → 2 pages
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "Finance" } });
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ department: "Finance", page: 1 })));
  });

  it("debounces text search and searches server-side", async () => {
    api.getEmployees.mockResolvedValue(EMP(1, [row("101", false)]));
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await screen.findByText("Person 101");
    const calls = api.getEmployees.mock.calls.length;
    const box = screen.getByLabelText("Search name, BHR ID or EMP Number");
    for (const v of ["P", "Pe", "Per"]) fireEvent.change(box, { target: { value: v } });
    expect(api.getEmployees.mock.calls.length).toBe(calls); // nothing sent per keystroke
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ q: "Per", page: 1 })));
  });
});

describe("Employee profile lazy loading", () => {
  it("loads the summary without raw events, then one day's events only when shown", async () => {
    setTestUrl("/employees?open=B101"); // profiles are addressed by BHR Employee ID
    api.getEmployees.mockResolvedValue(EMP(0, []));
    api.getEmployee.mockResolvedValue({ profile: { emp_code: "101", bamboohr_id: "B101", zk_emp_codes: ["101"], employee_name: "Person 101",
      department: "Finance", employment_status: "Active", identity_class: "MATCHED_ACTIVE", job_title: null, match_count: 1, has_photo: true },
    summary: { activity_days: 1, events: 2, review_flags: 0 }, events: [], directory_available: true,
    days: [{ local_date: "2026-11-03", emp_code: "101", first_activity_local: "2026-11-03T08:00:00+05:30", latest_activity_local: "2026-11-03T17:00:00+05:30",
      punch_count: 2, span_minutes: 540, terminal_names: ["Main Door"], identity_class: "MATCHED_ACTIVE", flags: [] }] });
    api.getActivity.mockResolvedValue({ total: 2, page: 1, page_size: 10, directory_available: true, items: [EVENT("101", "08:00"), EVENT("101", "17:00")] });
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    const dialog = await screen.findByRole("dialog");
    expect(api.getEmployee).toHaveBeenCalledWith("B101", expect.objectContaining({ include_events: false }));
    expect(await within(dialog).findByText("17:00")).toBeInTheDocument();
    expect(api.getActivity).toHaveBeenCalledWith(expect.objectContaining({ bamboohr_id: "B101", date_from: "2026-11-03", date_to: "2026-11-03", page_size: 10 }));
    expect(within(dialog).getByAltText("Profile photo of Person 101")).toBeInTheDocument();
  });
});

describe("Chart drill-down", () => {
  it("selecting a trend day focuses the whole overview on that day", async () => {
    setTestUrl("/?hour=11");
    api.getActivity.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /Tue 3 Nov 2026: 3 events/ }));
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledWith({ site_id: "colombo", date: "2026-11-03" }));
    expect(api.getOverview).toHaveBeenCalledWith({ site_id: "colombo", date: "2026-11-02" }); // complete day → comparison
    expect(api.getHourly).toHaveBeenLastCalledWith({ site_id: "colombo", date: "2026-11-03" });
    expect(getTestUrl().searchParams.get("hour")).toBeNull(); // no stale hour from another period
    expect(screen.getByText(/Selected day:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all events" })).toHaveAttribute("href", "/activity?from=2026-11-03&to=2026-11-03");
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    await waitFor(() => expect(getTestUrl().searchParams.get("from")).toBeNull());
  });

  it("selecting an hour opens exactly that hour's events, paged, and hands over to the employee profile", async () => {
    setTestUrl("/?from=2026-11-03&to=2026-11-03");
    api.getActivity.mockResolvedValue({ total: 3, page: 1, page_size: 10, directory_available: true,
      items: [EVENT("101", "11:05"), EVENT("102", "11:40"), EVENT("101", "11:59")] });
    api.getEmployee.mockResolvedValue({ profile: { emp_code: "101", bamboohr_id: "B101", employee_name: "Person 101", department: "Finance",
      employment_status: "Active", identity_class: "MATCHED_ACTIVE", job_title: null, match_count: 1 }, summary: { activity_days: 0, events: 0, review_flags: 0 }, days: [], events: [], directory_available: true });
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    const bar = await screen.findByRole("button", { name: /11:00–11:59 \(Asia\/Colombo\): 3 events/ });
    fireEvent.click(bar);
    const sheet = await screen.findByRole("dialog", { name: /11:00–11:59:59/ });
    await waitFor(() => expect(api.getActivity).toHaveBeenCalledWith(expect.objectContaining({
      date_from: "2026-11-03", date_to: "2026-11-03", hour: 11, page: 1, page_size: 10 })));
    expect(within(sheet).getByText("Team members with activity")).toBeInTheDocument();
    expect(within(sheet).getByText("2")).toBeInTheDocument();
    expect(within(sheet).getAllByText("Possible duplicate tap").length).toBeGreaterThan(0);
    expect(within(sheet).getByRole("link", { name: /View in Activity/ })).toHaveAttribute("href", "/activity?from=2026-11-03&to=2026-11-03&hour=11&sort=time");
    expect(bar).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(within(sheet).getAllByRole("button", { name: /Open Person 101/ })[0]);
    const profile = await screen.findByRole("dialog", { name: "Person 101" });
    fireEvent.keyDown(document, { key: "Escape" }); // closes only the top-most panel
    await waitFor(() => expect(profile).not.toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: /11:00–11:59:59/ })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(getTestUrl().searchParams.get("from")).toBe("2026-11-03"); // date selection preserved
  });

  it("explains an empty hour and labels multi-day hours as combined", async () => {
    setTestUrl("/?from=2026-10-29&to=2026-11-04&hour=3");
    api.getActivity.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByText("No activity recorded in this hour")).toBeInTheDocument();
    expect(within(sheet).getByText(/Combined across 7 days/)).toBeInTheDocument();
    expect(api.getActivity).toHaveBeenCalledWith(expect.objectContaining({ date_from: "2026-10-29", date_to: "2026-11-04", hour: 3 }));
    fireEvent.click(within(sheet).getByRole("button", { name: "Next hour" }));
    await waitFor(() => expect(getTestUrl().searchParams.get("hour")).toBe("4"));
  });

  it("Activity applies an hour filter from the URL and shows it as a chip", async () => {
    setTestUrl("/activity?from=2026-11-03&to=2026-11-03&hour=11&sort=time");
    api.getActivity.mockResolvedValue({ total: 1, page: 1, page_size: 10, directory_available: true, items: [EVENT("101", "11:05")] });
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    await waitFor(() => expect(api.getActivity).toHaveBeenCalledWith(expect.objectContaining({ hour: 11, sort: "time", page_size: 10 })));
    expect(await screen.findByRole("button", { name: /Remove filter: Hour: 11:00–11:59 \(Asia\/Colombo\)/ })).toBeInTheDocument();
  });
});
