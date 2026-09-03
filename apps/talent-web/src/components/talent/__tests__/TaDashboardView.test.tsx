import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getTaDashboard: vi.fn(),
  getRecruitmentFreshness: vi.fn(),
  getRecruitmentSyncRun: vi.fn(),
  listRecruitmentPostings: vi.fn(),
  requestRecruitmentSync: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { TaDashboardView } from "../TaDashboardView";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function dashboard(over: Partial<Record<string, unknown>> = {}) {
  return {
    clients: 3,
    active_requests: 5,
    active_applications: 7,
    available_candidates: 0,
    interviews_scheduled: 0,
    offers_in_progress: 0,
    pending_review_count: 0,
    attention_requests: [],
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getRecruitmentFreshness.mockResolvedValue({
    available: true, provider: "LEVER", last_successful_sync_at: null, latest_run: null,
  });
  api.listRecruitmentPostings.mockResolvedValue([]);
});

describe("TaDashboardView — dashboard click-through", () => {
  it("links Clients, Active Requests and Active Applications to their filtered list routes", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard());
    wrap(<TaDashboardView />);

    expect(await screen.findByText("Clients")).toBeInTheDocument();
    expect(screen.getByText("Clients").closest("a")).toHaveAttribute("href", "/clients");
    expect(screen.getByText("Active Requests").closest("a")).toHaveAttribute(
      "href",
      "/requests?status=active"
    );
    expect(screen.getByText("Active Applications").closest("a")).toHaveAttribute(
      "href",
      "/applications"
    );
  });

  it("never renders the Available Candidates widget", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard({ available_candidates: 0 }));
    wrap(<TaDashboardView />);

    await screen.findByText("Clients");
    expect(screen.queryByText("Available Candidates")).not.toBeInTheDocument();
  });

  it("Interviews Scheduled and Offers in Progress are non-clickable at zero", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard({ interviews_scheduled: 0, offers_in_progress: 0 }));
    wrap(<TaDashboardView />);

    await screen.findByText("Interviews Scheduled");
    expect(screen.getByText("Interviews Scheduled").closest("a")).toBeNull();
    expect(screen.getByText("Offers in Progress").closest("a")).toBeNull();
  });

  it("Interviews Scheduled and Offers in Progress become links once > 0", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard({ interviews_scheduled: 2, offers_in_progress: 1 }));
    wrap(<TaDashboardView />);

    await screen.findByText("Interviews Scheduled");
    expect(screen.getByText("Interviews Scheduled").closest("a")).toHaveAttribute("href", "/interviews");
    expect(screen.getByText("Offers in Progress").closest("a")).toHaveAttribute(
      "href",
      "/applications?status=OFFER"
    );
  });

  it("demotes Pending CS Review out of the primary metric grid but keeps it clickable when > 0", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard({ pending_review_count: 4 }));
    wrap(<TaDashboardView />);

    await screen.findByText("Clients");
    // Not a MetricCard in the primary grid any more.
    expect(screen.queryByText("Pending CS Review")).not.toBeInTheDocument();
    const link = screen.getByText("4 pending →");
    expect(link.closest("a")).toHaveAttribute("href", "/requests");
  });

  it("shows the pending count as plain text (not a link) when zero", async () => {
    api.getTaDashboard.mockResolvedValue(dashboard({ pending_review_count: 0 }));
    wrap(<TaDashboardView />);

    await screen.findByText("Clients");
    const text = screen.getByText("0 pending");
    expect(text.closest("a")).toBeNull();
  });
});
