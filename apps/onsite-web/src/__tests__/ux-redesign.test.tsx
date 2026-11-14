import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { getTestUrl, setTestUrl } from "@/test-navigation";
import { dayCount, normalizePeriod, presetOf, presetPeriod, previousPeriod } from "@/lib/period";

const ADMIN_PERMS = ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read", "onsite.health.read", "onsite.identity.read", "onsite.sites.manage", "onsite.sync.request"];
const VIEWER_PERMS = ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"];
const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_VIEWER", permissions: [] as string[] } } }));
vi.mock("@/lib/onsite-scope", async (orig) => ({ ...(await orig<typeof import("@/lib/onsite-scope")>()), useOnsiteScope: () => scope.value }));

const api = vi.hoisted(() => ({
  getSitesInfo: vi.fn(), getOverview: vi.fn(), getHourly: vi.fn(), getTrend: vi.fn(), getRecent: vi.fn(),
  getToday: vi.fn(), getActivity: vi.fn(), getEmployees: vi.fn(), getEmployee: vi.fn(), getExceptions: vi.fn(), downloadExport: vi.fn(),
}));
vi.mock("@/lib/dashboard", async (orig) => ({ ...(await orig<typeof import("@/lib/dashboard")>()), ...api }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), requestSync: vi.fn(), getSyncRun: vi.fn(),
  getFreshness: vi.fn().mockResolvedValue({ source_configured: true, last_successful_sync_at: new Date().toISOString(), latest_run: null,
    sites: [{ site_id: "colombo", feed_state: "FRESH", latest_received_utc: null, latest_punch_utc: null, agent_heartbeat_utc: null, agent_health: null }] }),
}));

// The site's own local "today" (Asia/Colombo) deliberately differs from the browser clock.
const SITE = { site_id: "colombo", name: "Colombo Office", time_zone: "Asia/Colombo", today: "2026-11-04",
  first_activity_date: "2024-11-27", last_activity_date: "2026-11-03", terminals: ["Main Door"], departments: ["Finance"] };
const FLAGS = { SINGLE_PUNCH: 3, POSSIBLE_DUPLICATE_TAP: 1, UNMATCHED_CODE: 2, AMBIGUOUS_CODE: 0, INACTIVE_EMPLOYEE_ACTIVITY: 0,
  BEFORE_HIRE_ACTIVITY: 0, TZ_INCONSISTENT: 0, HIGH_PUNCH_COUNT: 0 };
const overview = (events: number) => ({ site_id: "colombo", date: "x", time_zone: "Asia/Colombo", directory_available: true,
  kpis: { employees_with_activity: 10, total_events: events, activity_days: 1, employees_needing_review: 4, single_punch_employees: 3, unmatched_codes: 2, feed_state: "FRESH" },
  review_breakdown: FLAGS, last_successful_sync_at: null, latest_received_utc: null, agent_heartbeat_utc: null });
const DAY = (date: string, n = 2, flags: string[] = []) => ({ local_date: date, emp_code: "0107", employee_name: "Ishara G", department: "Finance",
  first_activity_local: `${date}T08:30:00+05:30`, latest_activity_local: `${date}T17:45:00+05:30`, punch_count: n, span_minutes: 555,
  terminal_names: ["Main Door"], identity_class: "MATCHED_ACTIVE", flags });

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function setMobile(mobile: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true, writable: true,
    value: mobile ? (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} }) : undefined,
  });
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  scope.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: VIEWER_PERMS } };
  api.getSitesInfo.mockResolvedValue([SITE]);
  api.getOverview.mockImplementation(async (p: { date?: string; date_from?: string }) => overview(p.date === "2026-11-02" ? 80 : 100));
  api.getHourly.mockResolvedValue({ hours: Array.from({ length: 24 }, (_, h) => ({ hour: h, events: h === 9 ? 7 : h === 8 ? 3 : 0, employees: 1 })) });
  api.getTrend.mockResolvedValue({ days: [{ date: "2026-11-02", events: 80, employees: 9 }, { date: "2026-11-03", events: 100, employees: 10 }] });
  api.getRecent.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
});
afterEach(() => setMobile(false));

describe("period helpers", () => {
  it("builds presets from the site-local today and caps ranges", () => {
    expect(presetPeriod("today", "2026-11-04")).toEqual({ from: "2026-11-04", to: "2026-11-04" });
    expect(presetPeriod("7d", "2026-11-04")).toEqual({ from: "2026-10-29", to: "2026-11-04" });
    expect(presetOf({ from: "2026-10-06", to: "2026-11-04" }, "2026-11-04")).toBe("30d");
    expect(previousPeriod({ from: "2026-10-29", to: "2026-11-04" })).toEqual({ from: "2026-10-22", to: "2026-10-28" });
    expect(dayCount(normalizePeriod({ from: "2026-01-01", to: "2026-11-04" }))).toBe(92);
    expect(normalizePeriod({ from: "2026-11-04", to: "2026-11-01" })).toEqual({ from: "2026-11-01", to: "2026-11-04" });
  });
});

describe("Overview", () => {
  it("defaults to the site-local today, not the browser date", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(api.getOverview).toHaveBeenCalledWith({ site_id: "colombo", date: "2026-11-04" });
  });

  it("never compares a day in progress, but compares complete periods with the previous one", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(screen.queryByText(/vs Mon 2 Nov/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yesterday" }));
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledWith({ site_id: "colombo", date: "2026-11-02" }));
    expect(await screen.findByText(/\+20/)).toBeInTheDocument(); // 100 events vs 80 the day before
    expect(getTestUrl().searchParams.get("from")).toBe("2026-11-03");
  });

  it("queries a range for Last 7 days", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: "Last 7 days" }));
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledWith({ site_id: "colombo", date_from: "2026-10-29", date_to: "2026-11-04" }));
    expect(api.getHourly).toHaveBeenCalledWith({ site_id: "colombo", date_from: "2026-10-29", date_to: "2026-11-04" });
  });

  it("links every KPI and review category to its supporting records", async () => {
    setTestUrl("/?from=2026-11-03&to=2026-11-03");
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(screen.getByRole("link", { name: /Employees with activity/ })).toHaveAttribute("href", "/today?date=2026-11-03");
    expect(screen.getByRole("link", { name: /Needing review/ })).toHaveAttribute("href", "/exceptions?from=2026-11-03&to=2026-11-03");
    expect(screen.getByRole("link", { name: /^Single activity.*View records/ })).toHaveAttribute("href", expect.stringContaining("flag=SINGLE_PUNCH"));
    // Unverified IDs are never part of viewer attendance: no unmapped/conflict category is offered.
    expect(screen.queryByRole("link", { name: /Unmapped ZKBioTime ID|Unmatched code/ })).not.toBeInTheDocument();
    // Feed → Site Health only for users who may open it.
    expect(screen.queryByRole("link", { name: /Feed/ })).not.toBeInTheDocument();
  });

  it("highlights the busiest hour and exposes exact values to keyboard users", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    await screen.findByText("Employees with activity");
    expect(screen.getByText("09:00")).toBeInTheDocument();
    const bar = screen.getByRole("button", { name: /09:00–09:59 \(Asia\/Colombo\): 7 events/ });
    fireEvent.focus(bar);
    expect(screen.getAllByRole("tooltip").some((t) => /09:00–09:59 \(Asia\/Colombo\)\s*7 events/.test(t.textContent ?? ""))).toBe(true);
  });

  it("explains an empty current day instead of implying absence", async () => {
    api.getOverview.mockResolvedValue({ ...overview(0), kpis: { ...overview(0).kpis, total_events: 0, employees_with_activity: 0 } });
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByText(/No activity has been recorded yet today/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View Tue 3 Nov/ }));
    await waitFor(() => expect(getTestUrl().searchParams.get("from")).toBe("2026-11-03"));
  });
});

describe("Exceptions drill-down", () => {
  it("applies the flag from the URL and keeps it while refreshing", async () => {
    api.getExceptions.mockResolvedValue({ total: 0, page: 1, page_size: 25, directory_available: true, counts: FLAGS, items: [] });
    setTestUrl("/exceptions?from=2026-11-03&to=2026-11-03&flag=SINGLE_PUNCH");
    const { default: Page } = await import("@/app/exceptions/page");
    renderPage(<Page />);
    await waitFor(() => expect(api.getExceptions).toHaveBeenCalledWith(expect.objectContaining({ flag: "SINGLE_PUNCH", date_from: "2026-11-03", date_to: "2026-11-03" })));
    expect(await screen.findByRole("button", { name: /^Single activity\s*3/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Remove filter: Single activity/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Remove filter: Single activity/ }));
    await waitFor(() => expect(getTestUrl().searchParams.get("flag")).toBeNull());
  });
});

describe("Responsive records", () => {
  const EMPLOYEES = { total: 1, page: 1, page_size: 50, date_from: "x", date_to: "y", departments: [], directory_available: true,
    summary: { employees: 3, with_activity: 1, active: 2, inactive: 1, not_in_directory: 0, needing_review: 1, matched: 3 },
    items: [{ emp_code: "0107", employee_name: "Ishara G", department: "Finance", employment_status: "Active", identity_class: "MATCHED_ACTIVE",
      in_directory: true, events: 6, activity_days: 3, review_flags: 1, last_activity_local: "2026-11-03T17:45:00+05:30" }] };

  it("renders a table on desktop", async () => {
    api.getEmployees.mockResolvedValue(EMPLOYEES);
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Events/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("renders cards, not a wide table, on phones", async () => {
    setMobile(true);
    api.getEmployees.mockResolvedValue(EMPLOYEES);
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    const list = await screen.findByRole("list", { name: /Employees,/ });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(within(list).getByText("Ishara G")).toBeInTheDocument();
    expect(within(list).getByText("Review flags")).toBeInTheDocument();
  });

  it("labels the population and sorts on the server", async () => {
    api.getEmployees.mockResolvedValue(EMPLOYEES);
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    expect(await screen.findByText("Employees in view")).toBeInTheDocument();
    expect(screen.getByText("2 · 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Employee$/ }));
    await waitFor(() => expect(api.getEmployees).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "-employee", page: 1 })));
  });
});

describe("Employee profile", () => {
  beforeEach(() => {
    api.getEmployees.mockResolvedValue({ total: 0, page: 1, page_size: 50, date_from: "x", date_to: "y", departments: [], directory_available: true, items: [] });
    api.getEmployee.mockResolvedValue({
      profile: { emp_code: "0107", employee_name: "Ishara G", department: "Finance", employment_status: "Active", identity_class: "MATCHED_ACTIVE", job_title: "Engineer", match_count: 1 },
      summary: { activity_days: 2, events: 5, review_flags: 1 },
      days: [DAY("2026-11-03", 3, ["POSSIBLE_DUPLICATE_TAP"]), DAY("2026-11-02", 2)],
      events: [
        { emp_code: "0107", employee_name: "Ishara G", department: "Finance", identity_class: "MATCHED_ACTIVE", local_date: "2026-11-02", local_time: "2026-11-02T08:30:00+05:30", terminal: "Main Door", area: null, punch_state_raw: "255", tz_consistent: true },
        { emp_code: "0107", employee_name: "Ishara G", department: "Finance", identity_class: "MATCHED_ACTIVE", local_date: "2026-11-03", local_time: "2026-11-03T08:30:00+05:30", terminal: "Main Door", area: null, punch_state_raw: "255", tz_consistent: true },
      ],
      directory_available: true,
    });
  });

  it("opens from the URL, summarises the period and inspects a selected day", async () => {
    setTestUrl("/employees?open=0107");
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    const dialog = await screen.findByRole("dialog", { name: "Ishara G" });
    expect(await within(dialog).findByText("Average per activity day")).toBeInTheDocument();
    expect(within(dialog).getByText("2.5")).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "Tue 3 Nov 2026" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /Mon 2 Nov 2026: 2 events/ }));
    expect(within(dialog).getByRole("heading", { name: "Mon 2 Nov 2026" })).toBeInTheDocument();
    expect(api.getEmployee).toHaveBeenCalledWith("0107", expect.objectContaining({ site_id: "colombo", date_to: "2026-11-04" }));
  });

  it("explains review flags and links to the supporting events", async () => {
    setTestUrl("/employees?open=0107");
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("tab", { name: /Review flags/ }));
    expect(within(dialog).getByText(/not confirmed policy breaches/)).toBeInTheDocument();
    expect(within(dialog).getByText(/within 60 seconds/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: /View events/ })).toHaveAttribute("href", "/activity?emp=0107&from=2026-11-03&to=2026-11-03");
  });

  it("moves focus in, closes on Escape and clears the URL", async () => {
    setTestUrl("/employees?open=0107");
    const { default: Page } = await import("@/app/employees/page");
    renderPage(<Page />);
    await screen.findByRole("dialog");
    expect(document.activeElement).toHaveAccessibleName(/Back|Close/);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(getTestUrl().searchParams.get("open")).toBeNull();
  });
});

describe("Mobile navigation", () => {
  it("marks the current page and keeps admin out of the bottom bar", async () => {
    setTestUrl("/today");
    const { MobileNav } = await import("@/components/MobileNav");
    render(<MobileNav />);
    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link")).toHaveLength(5);
    expect(screen.queryByRole("link", { name: /Site Health|Sites|Identity/ })).not.toBeInTheDocument();
  });
});

describe("Site Health permission", () => {
  it("offers Site Health from the Overview feed card only to admins", async () => {
    scope.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: ADMIN_PERMS } };
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByRole("link", { name: /Feed/ })).toHaveAttribute("href", "/admin/health");
  });
});
