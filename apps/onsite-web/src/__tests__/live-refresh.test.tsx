import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { LIVE_REFRESH_MS, liveQuery } from "@/lib/live-refresh";

const api = vi.hoisted(() => ({ getFreshness: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ago, FreshnessIndicator } from "@/components/FreshnessIndicator";

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const fresh = (feed: string, syncedAgoMs: number) => ({
  source_configured: true, latest_run: null,
  last_successful_sync_at: new Date(Date.now() - syncedAgoMs).toISOString(),
  sites: [{ site_id: "s1", feed_state: feed, latest_received_utc: null, latest_punch_utc: null, agent_heartbeat_utc: null, agent_health: null }],
});

describe("live refresh policy", () => {
  it("refetches every 30 seconds, only while visible, and keeps previous data", () => {
    expect(LIVE_REFRESH_MS).toBe(30_000);
    expect(liveQuery.refetchInterval).toBe(30_000);
    expect(liveQuery.refetchIntervalInBackground).toBe(false);
    expect(liveQuery.refetchOnWindowFocus).toBe(true);
    expect(liveQuery.placeholderData).toBeTypeOf("function");
  });

  it("uses the agreed relative wording", () => {
    const now = 1_000_000;
    expect(ago(now - 3_000, now)).toBe("just now");
    expect(ago(now - 31_000, now)).toBe("30 seconds ago");
    expect(ago(now - 125_000, now)).toBe("2 minutes ago");
    expect(ago(now - 60_000, now)).toBe("1 minute ago");
  });
});

describe("FreshnessIndicator", () => {
  const page = { dataUpdatedAt: Date.now(), isFetching: false, isError: false, refetch: vi.fn() };

  it("separates the page refresh from the mirror sync", async () => {
    api.getFreshness.mockResolvedValue(fresh("FRESH", 120_000));
    wrap(<FreshnessIndicator siteId="s1" queries={[page]} />);
    expect(await screen.findByText("Last synced 2 minutes ago")).toBeInTheDocument();
    expect(screen.getByText("Updated just now")).toBeInTheDocument();
    expect(screen.getByText("Feed current")).toBeInTheDocument();
    expect(screen.queryByText("Data may be delayed")).not.toBeInTheDocument();
  });

  it("never presents a successful page refresh as a current source", async () => {
    api.getFreshness.mockResolvedValue(fresh("DELAYED", 9 * 60_000));
    wrap(<FreshnessIndicator siteId="s1" queries={[page]} />);
    expect(await screen.findByText("Data may be delayed")).toBeInTheDocument();
    expect(screen.getByText("Updated just now")).toBeInTheDocument();
  });

  it("reports a failed refresh while keeping the loaded data, and offers Refresh", async () => {
    api.getFreshness.mockResolvedValue(fresh("FRESH", 10_000));
    const failed = { ...page, isError: true, refetch: vi.fn() };
    wrap(<FreshnessIndicator siteId="s1" queries={[failed]} />);
    expect(await screen.findByText(/Refresh failed — showing the last loaded data/)).toBeInTheDocument();
    await screen.findByText(/^Last synced/);
    fireEvent.click(screen.getByRole("button", { name: "Refresh now" }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});

describe("failed background refetch", () => {
  it("keeps previously loaded valid data", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    const fn = vi.fn(async () => {
      calls += 1;
      if (calls > 1) throw new Error("network");
      return { value: "first" };
    });
    function Probe() {
      const q = useQuery({ queryKey: ["probe"], queryFn: fn, ...liveQuery });
      return <p>{q.data ? `${q.data.value}${q.isError ? " (refresh failed)" : ""}` : "none"}</p>;
    }
    wrap(<Probe />);
    expect(await screen.findByText("first")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(LIVE_REFRESH_MS + 100); });
    expect(fn).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("first (refresh failed)")).toBeInTheDocument();
    vi.useRealTimers();
  });
});
