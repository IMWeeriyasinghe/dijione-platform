import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LayoutDashboard, Users } from "lucide-react";
import { AuthProvider } from "@dijione/auth-client";
import { AppShell } from "@dijione/design-system";
import { setTestUrl } from "@/test-navigation";

const scope = vi.hoisted(() => ({ value: { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } as { role: string; permissions: string[] } | null } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scope.value };
});
const api = vi.hoisted(() => ({
  getSitesInfo: vi.fn(), getOverview: vi.fn(), getHourly: vi.fn(), getTrend: vi.fn(), getRecent: vi.fn(),
  getActivity: vi.fn(), getEmployee: vi.fn(), downloadExport: vi.fn(),
}));
vi.mock("@/lib/dashboard", async (orig) => ({ ...(await orig<typeof import("@/lib/dashboard")>()), ...api }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()), requestSync: vi.fn(), getSyncRun: vi.fn(),
  getFreshness: vi.fn().mockResolvedValue({ source_configured: true, last_successful_sync_at: new Date().toISOString(), latest_run: null,
    sites: [{ site_id: "dev-site", feed_state: "FRESH", latest_received_utc: null, latest_punch_utc: null, agent_heartbeat_utc: null, agent_health: null }] }),
}));

const SITE = { site_id: "dev-site", name: "DEV Site (Colombo)", time_zone: "Asia/Colombo", today: "2026-11-18",
  first_activity_date: "2024-11-27", last_activity_date: "2026-11-18", terminals: ["Main Door"] };
const VERIFIED = { emp_code: "161", bamboohr_id: "297", employee_number: "161", mapping_status: "MAPPED", mapping_state: "VERIFIED",
  employee_name: "Verified Person", department: "Ops", identity_class: "MATCHED_ACTIVE", local_time: "2026-11-18T08:30:00+05:30",
  local_date: "2026-11-18", terminal: "Main Door", area: null, punch_state_raw: "0", tz_consistent: true, event_id: "e1",
  punch_sequence: "FIRST", punch_position: 1, punches_in_day: 3 };
const UNMAPPED = { emp_code: "352", bamboohr_id: null, employee_number: null, mapping_status: "UNMAPPED", mapping_state: "UNMAPPED",
  employee_name: null, department: null, identity_class: "UNMATCHED", local_time: "2026-11-18T09:05:00+05:30",
  local_date: "2026-11-18", terminal: "Main Door", area: null, punch_state_raw: "255", tz_consistent: true, event_id: "e2",
  punch_sequence: "SINGLE", punch_position: 1, punches_in_day: 1 };
const CONFLICT = { ...UNMAPPED, emp_code: "77", mapping_status: "MAPPING_CONFLICT", mapping_state: "CONFLICT", identity_class: "AMBIGUOUS",
  event_id: "e3", punch_sequence: "LAST", punch_position: 2, punches_in_day: 2 };
const SUMMARY = { recorded: 40, verified: 15, unverified: 25, unmapped: 24, conflict: 1 };

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  scope.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"] } };
  api.getSitesInfo.mockResolvedValue([SITE]);
  api.getActivity.mockResolvedValue({ total: 3, page: 1, page_size: 10, directory_available: true, mapping: "all", summary: SUMMARY,
    can_investigate_identity: false, items: [VERIFIED, UNMAPPED, CONFLICT] });
  setTestUrl("/activity");
});
afterEach(() => vi.unstubAllGlobals());

describe("Activity across mapping states", () => {
  it("defaults to All activity and reconciles recorded = verified + needs review", async () => {
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    await screen.findByRole("table", { name: "Recorded activity events" });
    expect(api.getActivity).toHaveBeenCalledWith(expect.objectContaining({ mapping: "all" }));
    const strip = screen.getByRole("group", { name: "Recorded events by mapping status" });
    expect(within(strip).getByRole("button", { name: /Recorded events\s*40/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(strip).getByRole("button", { name: /Verified\s*15/ })).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: /Unmapped \/ needs review\s*25.*24 unmapped · 1 conflict/ })).toBeInTheDocument();
  });

  it("shows unverified events by ZKBioTime ID only and keeps conflicts distinct", async () => {
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    const table = await screen.findByRole("table", { name: "Recorded activity events" });
    expect(within(table).getByText("Verified Person")).toBeInTheDocument();
    expect(within(table).getByText("352")).toBeInTheDocument();
    expect(within(table).getByText("Not mapped to a team member")).toBeInTheDocument();
    expect(within(table).getByText("Unmapped — needs review")).toBeInTheDocument();
    expect(within(table).getByText("Mapping conflict")).toBeInTheDocument();
    expect(within(table).getByText("Mapping conflict — not attributed")).toBeInTheDocument();
    // Whole-day sequence markers, never check-in / check-out.
    expect(within(table).getByText("First recorded")).toBeInTheDocument();
    expect(within(table).getByText("Single activity")).toBeInTheDocument();
    expect(within(table).queryByText(/^(check[- ]?in|check[- ]?out|in|out)$/i)).not.toBeInTheDocument();
  });

  it("only identity administrators get the route into Identity Management", async () => {
    const { default: Page } = await import("@/app/activity/page");
    const { unmount } = renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /Show details for ZKBioTime ID 352/ }));
    expect(screen.queryByRole("link", { name: /Investigate in Identity Management/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open team member profile/ })).not.toBeInTheDocument();
    unmount();
    api.getActivity.mockResolvedValue({ total: 1, page: 1, page_size: 10, directory_available: true, mapping: "all", summary: SUMMARY,
      can_investigate_identity: true, items: [UNMAPPED] });
    renderPage(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /Show details for ZKBioTime ID 352/ }));
    expect(screen.getByRole("link", { name: /Investigate in Identity Management/ })).toHaveAttribute("href", "/admin/identity?code=352");
  });

  it("filters by mapping state and keeps the export scope explicit", async () => {
    const { default: Page } = await import("@/app/activity/page");
    renderPage(<Page />);
    await screen.findByRole("table", { name: "Recorded activity events" });
    expect(screen.getByRole("button", { name: /Export to Excel \(recorded events\)/ })).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("group", { name: "Mapping status" })).getByRole("button", { name: "Verified" }));
    await waitFor(() => expect(api.getActivity).toHaveBeenLastCalledWith(expect.objectContaining({ mapping: "verified", page: 1 })));
    const exportButton = await screen.findByRole("button", { name: /Export to Excel \(verified attendance\)/ });
    fireEvent.click(exportButton);
    await waitFor(() => expect(api.downloadExport).toHaveBeenCalledWith("activity", expect.objectContaining({ mapping: "verified" })));
  });
});

describe("Overview charts include all recorded activity", () => {
  beforeEach(() => {
    setTestUrl("/");
    api.getOverview.mockResolvedValue({ site_id: "dev-site", date: "2026-11-18", time_zone: "Asia/Colombo", directory_available: true,
      kpis: { employees_with_activity: 3, total_events: 15, employees_needing_review: 0, single_punch_employees: 0, unmatched_codes: 0,
        feed_state: "FRESH", recorded_events: 40, verified_events: 15, unmapped_events: 24, conflict_events: 1 },
      review_breakdown: { SINGLE_PUNCH: 0, POSSIBLE_DUPLICATE_TAP: 0, UNMATCHED_CODE: 0, AMBIGUOUS_CODE: 0, INACTIVE_EMPLOYEE_ACTIVITY: 0,
        BEFORE_HIRE_ACTIVITY: 0, TZ_INCONSISTENT: 0, HIGH_PUNCH_COUNT: 0 },
      last_successful_sync_at: null, latest_received_utc: null, agent_heartbeat_utc: null });
    const zero = { verified: 0, unmapped: 0, conflict: 0 };
    api.getHourly.mockResolvedValue({ hours: Array.from({ length: 24 }, (_, h) => h === 8
      ? { hour: 8, events: 40, employees: 3, verified_events: 15, unmapped_events: 24, conflict_events: 1,
        first: { verified: 3, unmapped: 10, conflict: 0 }, last: zero, single: { verified: 0, unmapped: 4, conflict: 0 } }
      : { hour: h, events: 0, employees: 0, verified_events: 0, unmapped_events: 0, conflict_events: 0, first: zero, last: zero, single: zero }) });
    api.getTrend.mockResolvedValue({ days: [
      { date: "2026-11-17", events: 30, employees: 2, verified_events: 10, unmapped_events: 20, conflict_events: 0 },
      { date: "2026-11-18", events: 40, employees: 3, verified_events: 15, unmapped_events: 24, conflict_events: 1 }] });
    api.getRecent.mockResolvedValue({ total: 0, page: 1, page_size: 10, directory_available: true, items: [] });
  });

  it("stacks verified, unmapped and conflict, with first / last markers in the tooltip", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    expect(await screen.findByText("Recorded events")).toBeInTheDocument();
    expect(screen.getByText(/15 verified/)).toBeInTheDocument();
    const bar = screen.getByRole("button", { name: /08:00–08:59 \(Asia\/Colombo\): 40 recorded — 15 verified, 24 unmapped, 1 conflict/ });
    expect(bar.getAttribute("aria-label")).toMatch(/First recorded punch of the day: 13 · last: 0 · single: 4/);
    fireEvent.focus(bar);
    expect(screen.getAllByRole("tooltip").some((t) => /40 recorded.*15 verified.*24 unmapped.*1 conflict/.test(t.textContent ?? ""))).toBe(true);
    // The average describes the shown series: (30 + 40) / 2 recorded events per day.
    expect(screen.getByText(/avg 35 recorded\/day/)).toBeInTheDocument();
  });

  it("switching the series recomputes the average and carries the context into Activity", async () => {
    const { default: Page } = await import("@/app/page");
    renderPage(<Page />);
    await screen.findByText("Recorded events");
    fireEvent.click(within(screen.getByRole("group", { name: "Chart activity" })).getByRole("button", { name: "Verified" }));
    expect(await screen.findByText(/avg 13 verified\/day/)).toBeInTheDocument(); // (10 + 15) / 2 rounded
    expect(screen.getByRole("link", { name: /open these 30 days in Activity/ }).getAttribute("href")).toContain("mapping=verified");
  });
});

describe("Collapsible navigation (opt-in AppShell)", () => {
  const sections = [{ items: [{ label: "Overview", href: "/", icon: LayoutDashboard, exact: true }] },
    { label: "Admin", items: [{ label: "Team Members", href: "/employees", icon: Users }] }];
  const shell = (collapsible?: { storageKey: string }) => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}><AuthProvider>
        <AppShell title="Diji On-site" sections={sections} collapsible={collapsible}>content</AppShell>
      </AuthProvider></QueryClientProvider>,
    );
  };

  it("is absent unless the app opts in", () => {
    shell();
    expect(screen.queryByRole("button", { name: /Collapse navigation/ })).not.toBeInTheDocument();
  });

  it("collapses to an icon rail that keeps labels, admin items and the active page, and remembers it", () => {
    window.localStorage.removeItem("test.nav");
    setTestUrl("/employees");
    const { unmount } = shell({ storageKey: "test.nav" });
    const toggle = screen.getByRole("button", { name: "Collapse navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-expanded", "false");
    expect(window.localStorage.getItem("test.nav")).toBe("1");
    const active = screen.getAllByRole("link", { name: "Team Members" }).find((a) => a.getAttribute("aria-current") === "page");
    expect(active).toBeDefined();
    expect(active).toHaveAttribute("title", "Team Members");
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0); // section name kept for screen readers
    unmount();
    shell({ storageKey: "test.nav" });
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument(); // preference restored
  });
});
