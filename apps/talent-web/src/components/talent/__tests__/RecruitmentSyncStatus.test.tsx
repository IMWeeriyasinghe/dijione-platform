import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getRecruitmentFreshness: vi.fn(),
  getRecruitmentSyncRun: vi.fn(),
  listRecruitmentPostingsPaged: vi.fn(),
  requestRecruitmentSync: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { RecruitmentSyncStatus } from "../RecruitmentSyncStatus";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const run = (status: string) => ({
  run_id: "r1", provider: "LEVER", status, trigger_type: "SCHEDULED", requested_by_application: "x",
  requested_at: null, started_at: null, completed_at: null, records_read: 7, records_created: 0,
  records_updated: 0, records_unchanged: 0, error_summary: null,
});

const absolute = () => screen.getByTestId("last-sync-absolute");

beforeEach(() => {
  vi.clearAllMocks();
  api.listRecruitmentPostingsPaged.mockResolvedValue({
    items: [], total: 3, page: 1, page_size: 20, total_pages: 1,
    counts: { active: 0, verified: 0, unmapped: 0, review: 3, all: 0 },
  });
});
afterEach(() => vi.useRealTimers());

describe("RecruitmentSyncStatus — exact last successful sync time", () => {
  it("shows relative time, status and the absolute local timestamp with an accessible zone label", async () => {
    const t = new Date(Date.now() - 3 * 3_600_000).toISOString();
    api.getRecruitmentFreshness.mockResolvedValue({ provider: "LEVER", last_successful_sync_at: t, latest_run: run("SUCCEEDED") });
    wrap(<RecruitmentSyncStatus />);
    expect(await screen.findByText(/Last synced: 3 hrs ago · Up to date/)).toBeInTheDocument();
    const el = absolute().closest("time")!;
    expect(el).toHaveAttribute("dateTime", new Date(t).toISOString());
    expect(el.textContent).toMatch(/^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{1,2}:\d{2} (AM|PM)$/);
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(el.getAttribute("title")).toContain(`(${zone})`);
    // the full, zone-qualified form is also in the accessible text
    expect(screen.getByText(`(${el.getAttribute("title")})`, { exact: false })).toHaveClass("sr-only");
  });

  it("keeps the last SUCCESSFUL timestamp when the latest run failed", async () => {
    const t = "2026-11-13T05:00:00+00:00";
    api.getRecruitmentFreshness.mockResolvedValue({ provider: "LEVER", last_successful_sync_at: t, latest_run: run("FAILED") });
    wrap(<RecruitmentSyncStatus />);
    expect(await screen.findByText(/· Last sync failed/)).toBeInTheDocument();
    expect(absolute().closest("time")).toHaveAttribute("dateTime", "2026-11-13T05:00:00.000Z");
  });

  it("shows a placeholder, never an invented date, when nothing has succeeded", async () => {
    api.getRecruitmentFreshness.mockResolvedValue({ provider: "LEVER", last_successful_sync_at: null, latest_run: run("FAILED") });
    wrap(<RecruitmentSyncStatus />);
    expect(await screen.findByText(/Last synced: never · Last sync failed/)).toBeInTheDocument();
    expect(absolute()).toHaveTextContent("No successful sync recorded yet");
    expect(document.querySelector("time")).toBeNull();
  });

  it("after Sync now succeeds, refreshes the timestamp from the backend result", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const before = "2026-11-13T05:00:00+00:00";
    const after = "2026-11-13T11:00:00+00:00";
    api.getRecruitmentFreshness
      .mockResolvedValueOnce({ provider: "LEVER", last_successful_sync_at: before, latest_run: run("SUCCEEDED") })
      .mockResolvedValue({ provider: "LEVER", last_successful_sync_at: after, latest_run: run("SUCCEEDED") });
    api.requestRecruitmentSync.mockResolvedValue({ run_id: "r2", status: "QUEUED", started: true, message: "" });
    api.getRecruitmentSyncRun.mockResolvedValue({ run: run("SUCCEEDED") });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    wrap(<RecruitmentSyncStatus />);
    await screen.findByText(/Up to date/);
    expect(absolute().closest("time")).toHaveAttribute("dateTime", "2026-11-13T05:00:00.000Z");
    await user.click(screen.getByRole("button", { name: /Sync now/ }));
    await act(async () => { vi.advanceTimersByTime(3_100); });
    expect(await screen.findByText(/Recruitment data updated/)).toBeInTheDocument();
    expect(absolute().closest("time")).toHaveAttribute("dateTime", "2026-11-13T11:00:00.000Z");
  });

  it("gets the needs-review count from one small paged request, not every posting", async () => {
    api.getRecruitmentFreshness.mockResolvedValue({ provider: "LEVER", last_successful_sync_at: null, latest_run: null });
    wrap(<RecruitmentSyncStatus />);
    expect(await screen.findByText(/3 postings need client mapping review/)).toBeInTheDocument();
    expect(api.listRecruitmentPostingsPaged).toHaveBeenCalledWith({ view: "review", page: 1, page_size: 20 });
  });
});
