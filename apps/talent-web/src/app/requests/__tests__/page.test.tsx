import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ listTalentRequestsPaged: vi.fn() }));
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

/** Server-like fake for /requests/paged: resolves "active" to
 * APPROVED + IN_PROGRESS, applies other filters, returns one page. */
function serve(rows: ReturnType<typeof request>[]) {
  api.listTalentRequestsPaged.mockImplementation(
    async (p: { status_filter?: string; stage?: string; page: number; page_size: number }) => {
      const matched = rows.filter((r) =>
        !p.status_filter
          ? true
          : p.status_filter === "active"
            ? ["APPROVED", "IN_PROGRESS"].includes(r.lifecycle_status as string)
            : r.lifecycle_status === p.status_filter,
      ).filter((r) => !p.stage || r.current_stage === p.stage);
      const start = (p.page - 1) * p.page_size;
      return {
        items: matched.slice(start, start + p.page_size),
        total: matched.length,
        page: p.page,
        page_size: p.page_size,
        total_pages: Math.max(1, Math.ceil(matched.length / p.page_size)),
      };
    },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  currentParams = new URLSearchParams();
  authClient.useTalentScope.mockReturnValue({ isStaff: true, client_id: null, client_ids: null });
});

describe("RequestsPage — ?status=active click-through", () => {
  it("filters to the dashboard's Active Requests definition (APPROVED + IN_PROGRESS only)", async () => {
    currentParams = new URLSearchParams("status=active");
    serve([
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

    // "active" is resolved server-side so totals/pages are exact.
    expect(api.listTalentRequestsPaged).toHaveBeenCalledWith(
      expect.objectContaining({ status_filter: "active", page: 1, page_size: 12 })
    );
    expect(screen.getByText("Showing 1–2 of 2 requests")).toBeInTheDocument();
  });

  it("applies client_id from the URL for a staff caller", async () => {
    currentParams = new URLSearchParams("client_id=42");
    serve([request()]);

    wrap();

    await screen.findByText("Role");
    expect(api.listTalentRequestsPaged).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: 42 })
    );
  });

  it("with no status param, shows every row and sends no status_filter", async () => {
    serve([
      request({ designation: "A", lifecycle_status: "APPROVED" }),
      request({ designation: "B", lifecycle_status: "FULFILLED" }),
    ]);

    wrap();

    expect(await screen.findByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(api.listTalentRequestsPaged).toHaveBeenCalledWith(
      expect.objectContaining({ status_filter: undefined })
    );
  });
});

describe("RequestsPage — server-side pagination", () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) => request({ id: i + 1, designation: `Role ${i + 1}`, current_stage: i % 2 ? "SOURCING" : "SCREENING" }));

  it("defaults to 12 cards in a 3/2/1-column grid, with 12/24/48/96 sizes", async () => {
    serve(many(40));
    wrap();
    expect(await screen.findByText("Showing 1–12 of 40 requests")).toBeInTheDocument();
    const grid = screen.getByText("Role 1").closest("div.grid") as HTMLElement;
    expect(grid.className).toMatch(/sm:grid-cols-2/);
    expect(grid.className).toMatch(/lg:grid-cols-3/);
    expect(grid.children).toHaveLength(12);
    const opts = [...(screen.getByLabelText("Requests per page") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toEqual(["12", "24", "48", "96"]);
  });

  it("numbered navigation with an active page, and a filter change resets to page 1", async () => {
    const user = userEvent.setup();
    serve(many(40));
    wrap();
    await screen.findByText("Showing 1–12 of 40 requests");
    await user.click(screen.getByLabelText("Page 2"));
    expect(await screen.findByText("Showing 13–24 of 40 requests")).toBeInTheDocument();
    expect(screen.getByLabelText("Page 2")).toHaveAttribute("aria-current", "page");
    await user.selectOptions(screen.getByLabelText("Filter by stage"), "SOURCING");
    expect(await screen.findByText("Showing 1–12 of 20 requests")).toBeInTheDocument();
    expect(api.listTalentRequestsPaged).toHaveBeenLastCalledWith(
      expect.objectContaining({ stage: "SOURCING", page: 1, page_size: 12 }),
    );
  });

  it("changing page size keeps working from page 1", async () => {
    const user = userEvent.setup();
    serve(many(40));
    wrap();
    await screen.findByText("Showing 1–12 of 40 requests");
    await user.click(screen.getByLabelText("Last page"));
    await screen.findByText("Showing 37–40 of 40 requests");
    await user.selectOptions(screen.getByLabelText("Requests per page"), "24");
    expect(await screen.findByText("Showing 1–24 of 40 requests")).toBeInTheDocument();
  });

  it("shows the empty state when nothing matches", async () => {
    serve([]);
    wrap();
    expect(await screen.findByText("No requests found")).toBeInTheDocument();
    expect(screen.queryByLabelText("Request pagination")).not.toBeInTheDocument();
  });
});
