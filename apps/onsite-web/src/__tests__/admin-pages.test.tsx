import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { IdentityReport, OnsiteSite, SiteHealth } from "@/lib/types";

vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => ({ loading: false, scope: { role: "ONSITE_ADMIN", isAdmin: true } }) };
});

const api = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getSyncHistory: vi.fn(),
  getSyncRun: vi.fn(),
  requestSync: vi.fn(),
  getSites: vi.fn(),
  setSiteEnabled: vi.fn(),
  getIdentityReport: vi.fn(),
  downloadIdentityCsv: vi.fn(),
  getFreshness: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const HEALTH: SiteHealth = {
  last_successful_sync_at: "2026-10-22T00:00:00Z",
  latest_run: null,
  sites: [
    { site_id: "dev-site", feed_state: "STALE", latest_received_utc: null, latest_punch_utc: null,
      agent_heartbeat_utc: null, agent_health: null },
    { site_id: "syd-site", feed_state: "SOURCE_UNAVAILABLE", latest_received_utc: null, latest_punch_utc: null,
      agent_heartbeat_utc: null, agent_health: null },
  ],
  reconciliation: [
    { site_id: "dev-site", source_epoch: 1000, source_count: 42864, mirror_count: 42864,
      source_max_received_utc: null, mirror_max_received_utc: null, in_sync: true },
    { site_id: "dev-site", source_epoch: 1, source_count: 10, mirror_count: 9,
      source_max_received_utc: null, mirror_max_received_utc: null, in_sync: false },
  ],
};

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getHealth.mockResolvedValue(HEALTH);
  api.getSyncHistory.mockResolvedValue([]);
});

describe("Site Health", () => {
  it("renders feed states, reconciliation and drift", async () => {
    const { default: Page } = await import("@/app/admin/health/page");
    renderWithQuery(<Page />);
    expect(await screen.findByText("Feed stale")).toBeInTheDocument();
    expect(screen.getByText("Source unavailable")).toBeInTheDocument();
    expect(screen.getByText("In sync")).toBeInTheDocument();
    expect(screen.getByText("Drift")).toBeInTheDocument();
  });

  it("Sync now requests a sync and follows the run", async () => {
    api.requestSync.mockResolvedValue({ run_id: "r1", status: "QUEUED", started: true, message: "Sync started" });
    api.getSyncRun.mockResolvedValue({ run_id: "r1", status: "SUCCEEDED", events_inserted: 3, events_existing: 5, source_unavailable: false });
    const { default: Page } = await import("@/app/admin/health/page");
    renderWithQuery(<Page />);
    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));
    await waitFor(() => expect(api.requestSync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/3 new event/)).toBeInTheDocument(), { timeout: 5000 });
  });
});

describe("Sites", () => {
  it("lists discovered sites and toggles enablement", async () => {
    const sites: OnsiteSite[] = [
      { site_id: "dev-site", enabled: false, label: null, display_name: "DEV Site", time_zone: "Asia/Colombo",
        source_active: true, expected_location_values: null, last_seen_at: null },
    ];
    api.getSites.mockResolvedValue(sites);
    api.setSiteEnabled.mockResolvedValue({ ...sites[0], enabled: true });
    const { default: Page } = await import("@/app/admin/sites/page");
    renderWithQuery(<Page />);
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enable" }));
    await waitFor(() => expect(api.setSiteEnabled).toHaveBeenCalledWith("dev-site", true));
  });
});

describe("Identity Match", () => {
  const report: IdentityReport = {
    directory_available: true,
    summary: { MATCHED_ACTIVE: 2, MATCHED_INACTIVE: 1, MATCHED_BEFORE_HIRE: 0, AMBIGUOUS: 1, UNMATCHED: 1,
      directory_total: 528, directory_blank_employee_numbers: 24, directory_duplicate_employee_numbers: 0,
      directory_entries_without_attendance: 100 },
    rows: [
      { emp_code: "0107", identity_class: "MATCHED_ACTIVE", event_count: 5, first_seen: "2026-01-01", last_seen: "2026-02-01", matches: [] },
      { emp_code: "999", identity_class: "UNMATCHED", event_count: 1, first_seen: "2026-01-01", last_seen: "2026-01-01", matches: [] },
    ],
  };

  it("renders classes, codes verbatim and exports CSV", async () => {
    api.getIdentityReport.mockResolvedValue(report);
    api.downloadIdentityCsv.mockResolvedValue(undefined);
    const { default: Page } = await import("@/app/admin/identity/page");
    renderWithQuery(<Page />);
    expect(await screen.findByText("0107")).toBeInTheDocument();
    expect(screen.getAllByText("No matching Employee Number").length).toBeGreaterThan(0);
    expect(screen.getByText(/528 employees/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(api.downloadIdentityCsv).toHaveBeenCalled());
  });

  it("shows codes only when the Workforce Directory is unavailable", async () => {
    api.getIdentityReport.mockResolvedValue({
      directory_available: false, summary: { attendance_emp_codes: 1 },
      rows: [{ emp_code: "101", identity_class: null, event_count: 2, first_seen: "2026-01-01", last_seen: "2026-01-02", matches: [] }],
    });
    const { default: Page } = await import("@/app/admin/identity/page");
    renderWithQuery(<Page />);
    expect(await screen.findByText(/Employee details unavailable — the Workforce Directory/)).toBeInTheDocument();
    expect(screen.getByText("101")).toBeInTheDocument();
  });
});
