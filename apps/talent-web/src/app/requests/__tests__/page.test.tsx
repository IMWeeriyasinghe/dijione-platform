import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ listTalentRequests: vi.fn() }));
vi.mock("@/lib/api", () => api);

const authClient = vi.hoisted(() => ({ useTalentScope: vi.fn() }));
vi.mock("@dijione/auth-client", () => authClient);

let currentParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => currentParams,
}));

import RequestsPage from "../page";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequestsPage />
    </QueryClientProvider>
  );
}

function request(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: Math.floor(Math.random() * 1e6),
    request_code: "TA-0001",
    client_id: 1,
    client_name: "ABC Company",
    designation: "Role",
    description: "",
    current_stage: "SOURCING",
    lifecycle_status: "APPROVED",
    customer_success_status: "APPROVED",
    ta_status: "IN_PROGRESS",
    client_safe_status_text: "",
    stage_timeline: [],
    progress_percent: 0,
    active_application_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  currentParams = new URLSearchParams();
  authClient.useTalentScope.mockReturnValue({ isStaff: true, client_id: null, client_ids: null });
});

describe("RequestsPage — ?status=active click-through", () => {
  it("filters to the dashboard's Active Requests definition (APPROVED + IN_PROGRESS only)", async () => {
    currentParams = new URLSearchParams("status=active");
    api.listTalentRequests.mockResolvedValue([
      request({ designation: "Approved Role", lifecycle_status: "APPROVED" }),
      request({ designation: "In Progress Role", lifecycle_status: "IN_PROGRESS" }),
      request({ designation: "Pending Role", lifecycle_status: "PENDING_REVIEW" }),
      request({ designation: "Fulfilled Role", lifecycle_status: "FULFILLED" }),
    ]);

    wrap();

    expect(await screen.findByText("Approved Role")).toBeInTheDocument();
    expect(screen.getByText("In Progress Role")).toBeInTheDocument();
    expect(screen.queryByText("Pending Role")).not.toBeInTheDocument();
    expect(screen.queryByText("Fulfilled Role")).not.toBeInTheDocument();

    // "active" is a frontend-only pseudo-filter — never sent to the API.
    expect(api.listTalentRequests).toHaveBeenCalledWith(
      expect.objectContaining({ status_filter: undefined })
    );
  });

  it("applies client_id from the URL for a staff caller", async () => {
    currentParams = new URLSearchParams("client_id=42");
    api.listTalentRequests.mockResolvedValue([request()]);

    wrap();

    await screen.findByText("Role");
    expect(api.listTalentRequests).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: 42 })
    );
  });

  it("with no status param, shows every row and sends no status_filter", async () => {
    api.listTalentRequests.mockResolvedValue([
      request({ designation: "A", lifecycle_status: "APPROVED" }),
      request({ designation: "B", lifecycle_status: "FULFILLED" }),
    ]);

    wrap();

    expect(await screen.findByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(api.listTalentRequests).toHaveBeenCalledWith(
      expect.objectContaining({ status_filter: undefined })
    );
  });
});
