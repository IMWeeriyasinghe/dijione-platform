import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ listClientPortfolios: vi.fn() }));
vi.mock("@/lib/api", () => api);

import ClientPortfoliosPage from "../page";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ClientPortfoliosPage />
    </QueryClientProvider>
  );
}

function client(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    name: "Simple Biz",
    industry: null,
    account_manager: null,
    status: "ACTIVE",
    created_at: "2026-01-01T00:00:00Z",
    total_requests: 6,
    active_requests: 2,
    active_application_count: 3,
    client_visible_count: 4,
    latest_request_at: "2026-08-12T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ClientPortfoliosPage — card view + click-through", () => {
  it("defaults to card view showing the richer metrics with correct links", async () => {
    api.listClientPortfolios.mockResolvedValue([client()]);
    wrap();

    expect(await screen.findByText("Simple Biz")).toBeInTheDocument();
    expect(screen.getByText("6 requests")).toBeInTheDocument();
    expect(screen.getByText("2 active")).toBeInTheDocument();
    expect(screen.getByText(/4/)).toBeInTheDocument(); // shared-with-client count

    expect(screen.getByRole("link", { name: "Simple Biz" })).toHaveAttribute("href", "/clients/1");
    expect(screen.getByText("6 requests").closest("a")).toHaveAttribute("href", "/requests?client_id=1");
    expect(screen.getByText("2 active").closest("a")).toHaveAttribute(
      "href",
      "/requests?client_id=1&status=active"
    );
  });

  it("shows 'No requests yet' instead of a fabricated date when latest_request_at is null", async () => {
    api.listClientPortfolios.mockResolvedValue([client({ latest_request_at: null })]);
    wrap();

    await screen.findByText("Simple Biz");
    expect(screen.getByText("No requests yet")).toBeInTheDocument();
  });

  it("switches to table view and keeps the same click-through links", async () => {
    const user = userEvent.setup();
    api.listClientPortfolios.mockResolvedValue([client()]);
    wrap();

    await screen.findByText("Simple Biz");
    await user.click(screen.getByRole("button", { name: /table/i }));

    expect(screen.getByRole("columnheader", { name: "Total Requests" })).toBeInTheDocument();
    const row = screen.getByText("Simple Biz").closest("tr");
    expect(row).not.toBeNull();
    expect(screen.getByText("6").closest("a")).toHaveAttribute("href", "/requests?client_id=1");
  });

  it("does not show industry/account manager columns (no real data source yet)", async () => {
    api.listClientPortfolios.mockResolvedValue([client()]);
    wrap();

    await screen.findByText("Simple Biz");
    expect(screen.queryByText(/industry/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/account manager/i)).not.toBeInTheDocument();
  });
});
