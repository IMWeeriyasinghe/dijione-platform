import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listRecruitmentPostingsPaged: vi.fn(),
  listClientPortfolios: vi.fn(),
  verifyPostingMapping: vi.fn(),
  unmapPostingMapping: vi.fn(),
  reopenPostingMapping: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { PostingsView } from "../PostingsView";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function posting(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: Math.floor(Math.random() * 1e6),
    external_id: "uuid",
    provider: "LEVER",
    title: "Role",
    state: "published",
    location: "",
    archived: false,
    lever_created_at: "2026-08-01T00:00:00Z",
    mapping_status: "UNMAPPED",
    mapping_client_id: null,
    mapping_client_name: null,
    mapping_source: "",
    dtc_source_tag: null,
    dtc_client_name: null,
    resolution_status: "NO_DTC_TAG",
    ...over,
  };
}

const REVIEW = ["UNKNOWN_CLIENT_IDENTIFIER", "AMBIGUOUS_MULTIPLE_TAGS", "AMBIGUOUS_CLIENT_NAME", "MALFORMED_TAG", "CONFLICT_MANUAL_OVERRIDE"];
const VIEWS: Record<string, (p: ReturnType<typeof posting>) => boolean> = {
  active: (p) => p.state !== "closed",
  verified: (p) => p.mapping_status === "VERIFIED",
  unmapped: (p) => p.mapping_status === "UNMAPPED",
  review: (p) => p.mapping_status !== "VERIFIED" && REVIEW.includes(p.resolution_status as string),
  all: () => true,
};

/** Server-like fake for /postings/paged: view filter, page and counts. */
function serve(rows: ReturnType<typeof posting>[]) {
  api.listRecruitmentPostingsPaged.mockImplementation(
    async ({ view, page, page_size }: { view: string; page: number; page_size: number }) => {
      const matched = rows.filter(VIEWS[view]);
      const start = (page - 1) * page_size;
      return {
        items: matched.slice(start, start + page_size),
        total: matched.length,
        page,
        page_size,
        total_pages: Math.max(1, Math.ceil(matched.length / page_size)),
        counts: Object.fromEntries(Object.entries(VIEWS).map(([k, f]) => [k, rows.filter(f).length])),
      };
    },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  api.listClientPortfolios.mockResolvedValue([]);
  serve([
    posting({ title: "Open A", state: "published", mapping_status: "VERIFIED" }),
    posting({ title: "Open B", state: "internal", mapping_status: "UNMAPPED" }),
    posting({ title: "Old closed 1", state: "closed", mapping_status: "UNMAPPED" }),
    posting({ title: "Old closed 2", state: "closed", mapping_status: "UNMAPPED" }),
    posting({ title: "Old closed 3", state: "closed", mapping_status: "VERIFIED" }),
  ]);
});

describe("PostingsView filter chips", () => {
  it("defaults to non-closed postings and hides the closed backlog", async () => {
    wrap(<PostingsView />);
    expect(await screen.findByText("Open A")).toBeInTheDocument();
    expect(screen.getByText("Open B")).toBeInTheDocument();
    expect(screen.queryByText("Old closed 1")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1–2 of 2 postings")).toBeInTheDocument();
    expect(screen.getByText(/3 closed\/older postings hidden/)).toBeInTheDocument();
    expect(api.listRecruitmentPostingsPaged).toHaveBeenCalledWith({ view: "active", page: 1, page_size: 20 });
  });

  it('"All" reveals every posting', async () => {
    const user = userEvent.setup();
    wrap(<PostingsView />);
    await screen.findByText("Open A");
    await user.click(screen.getByRole("button", { name: /^All / }));
    expect(await screen.findByText("Old closed 1")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–5 of 5 postings")).toBeInTheDocument();
  });

  it('"Verified" shows only VERIFIED postings, across all states', async () => {
    const user = userEvent.setup();
    wrap(<PostingsView />);
    await screen.findByText("Open A");
    await user.click(screen.getByRole("button", { name: /^Verified / }));
    expect(await screen.findByText("Old closed 3")).toBeInTheDocument();
    expect(screen.getByText("Open A")).toBeInTheDocument();
    expect(screen.getByText("Old closed 3")).toBeInTheDocument(); // verified-but-closed still shown
    expect(screen.queryByText("Open B")).not.toBeInTheDocument();
  });
});

describe("PostingsView — Created column", () => {
  it("shows the formatted lever_created_at, or a dash when absent", async () => {
    serve([
      posting({ title: "Has Date", lever_created_at: "2026-08-12T00:00:00Z" }),
      posting({ title: "No Date", lever_created_at: null }),
    ]);
    wrap(<PostingsView />);
    await screen.findByText("Has Date");
    // formatDate uses the runtime's default locale (day/month order
    // differs between environments) — match on content, not exact
    // formatting, to avoid a CI-vs-local locale mismatch.
    expect(screen.getByText((text) => text.includes("2026") && text.includes("Aug"))).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("PostingsView — four mapping states", () => {
  it("labels auto-verified, manually verified, manually unmapped and unmapped distinctly", async () => {
    serve([
      posting({ title: "Auto", mapping_status: "VERIFIED", mapping_source: "LEVER_DTC_TAG" }),
      posting({ title: "Manual", mapping_status: "VERIFIED", mapping_source: "MANUAL" }),
      posting({ title: "Unmapped-manually", mapping_status: "REJECTED", mapping_source: "MANUAL" }),
      posting({ title: "Plain", mapping_status: "UNMAPPED", mapping_source: "" }),
    ]);
    wrap(<PostingsView />);
    await screen.findByText("Auto");
    const table = screen.getByRole("table");
    expect(within(table).getByText("Auto-verified")).toBeInTheDocument();
    expect(within(table).getByText("Manually verified")).toBeInTheDocument();
    expect(within(table).getByText("Manually unmapped")).toBeInTheDocument();
    // "Unmapped" also appears as filter-chip text outside the table, so
    // this query is scoped to table rows to avoid ambiguity.
    expect(within(table).getByText("Unmapped")).toBeInTheDocument();
  });
});

describe("PostingsView — unmap / reopen", () => {
  it("Unmap opens a confirmation, then calls the API and refreshes on confirm", async () => {
    const user = userEvent.setup();
    serve([
      posting({
        id: 501, title: "Verified Role", mapping_status: "VERIFIED", mapping_source: "MANUAL",
        mapping_client_name: "ABC Company",
      }),
    ]);
    api.unmapPostingMapping.mockResolvedValue(
      posting({ id: 501, title: "Verified Role", mapping_status: "REJECTED", mapping_source: "MANUAL" })
    );
    wrap(<PostingsView />);

    await user.click(await screen.findByRole("button", { name: "Unmap" }));
    expect(await screen.findByText(/Remove client mapping\?/)).toBeInTheDocument();

    // Two "Unmap" buttons now exist: the row's ghost trigger and the
    // modal's confirm action (which is last in DOM order).
    const unmapButtons = screen.getAllByRole("button", { name: "Unmap" });
    await user.click(unmapButtons[unmapButtons.length - 1]);
    expect(api.unmapPostingMapping).toHaveBeenCalledWith(501);
  });

  it("Cancel on the confirmation does not call the API", async () => {
    const user = userEvent.setup();
    serve([
      posting({ id: 502, title: "Verified Role", mapping_status: "VERIFIED", mapping_source: "MANUAL" }),
    ]);
    wrap(<PostingsView />);

    await user.click(await screen.findByRole("button", { name: "Unmap" }));
    await screen.findByText(/Remove client mapping\?/);
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText(/Remove client mapping\?/)).not.toBeInTheDocument();
    expect(api.unmapPostingMapping).not.toHaveBeenCalled();
  });

  it("a manually-unmapped posting shows Reopen instead of Verify/Unmap", async () => {
    const user = userEvent.setup();
    serve([
      posting({ id: 503, title: "Unmapped Role", mapping_status: "REJECTED", mapping_source: "MANUAL" }),
    ]);
    api.reopenPostingMapping.mockResolvedValue(
      posting({ id: 503, title: "Unmapped Role", mapping_status: "UNMAPPED", mapping_source: "" })
    );
    wrap(<PostingsView />);

    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unmap" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verify manually" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reopen" }));
    expect(api.reopenPostingMapping).toHaveBeenCalledWith(503);
  });

  it("a plain unmapped posting has no Unmap action, only Verify manually", async () => {
    serve([
      posting({ id: 504, title: "Fresh Role", mapping_status: "UNMAPPED", mapping_source: "" }),
    ]);
    wrap(<PostingsView />);

    expect(await screen.findByRole("button", { name: "Verify manually" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unmap" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });
});

describe("PostingsView — server-side pagination", () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      posting({ id: i + 1, title: `P${i + 1}`, state: i < 30 ? "closed" : "published", mapping_status: i % 4 ? "UNMAPPED" : "VERIFIED" }),
    );

  it("defaults to 20 rows per page with 20/50/100 and server chip counts", async () => {
    serve(many(130));
    wrap(<PostingsView />);
    expect(await screen.findByText("Showing 1–20 of 100 postings")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Recent \/ Active \(100\)/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^All \(130\)/ })).toBeInTheDocument();
    const opts = [...(screen.getByLabelText("Postings per page") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toEqual(["20", "50", "100"]);
  });

  it("changing the filter returns to page 1 and keeps the page size", async () => {
    const user = userEvent.setup();
    serve(many(130));
    wrap(<PostingsView />);
    await screen.findByText("Showing 1–20 of 100 postings");
    await user.selectOptions(screen.getByLabelText("Postings per page"), "50");
    await user.click(await screen.findByLabelText("Page 2"));
    await screen.findByText("Showing 51–100 of 100 postings");
    await user.click(screen.getByRole("button", { name: /^All / }));
    expect(await screen.findByText("Showing 1–50 of 130 postings")).toBeInTheDocument();
    expect(api.listRecruitmentPostingsPaged).toHaveBeenLastCalledWith({ view: "all", page: 1, page_size: 50 });
  });
});
