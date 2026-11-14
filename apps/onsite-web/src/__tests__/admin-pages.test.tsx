import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { OnsiteSite, SiteHealth } from "@/lib/types";

vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => ({ loading: false, scope: { role: "ONSITE_ADMIN", permissions: ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read", "onsite.health.read", "onsite.identity.read", "onsite.sites.manage", "onsite.sync.request"] } }) };
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
