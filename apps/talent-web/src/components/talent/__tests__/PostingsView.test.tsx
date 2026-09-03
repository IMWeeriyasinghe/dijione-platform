import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listRecruitmentPostings: vi.fn(),
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

beforeEach(() => {
  vi.clearAllMocks();
  api.listClientPortfolios.mockResolvedValue([]);
  api.listRecruitmentPostings.mockResolvedValue([
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
    expect(screen.getByText(/Showing 2 of 5 postings/)).toBeInTheDocument();
    expect(screen.getByText(/3 closed\/older hidden/)).toBeInTheDocument();
  });

  it('"All" reveals every posting', async () => {
    const user = userEvent.setup();
    wrap(<PostingsView />);
    await screen.findByText("Open A");
    await user.click(screen.getByRole("button", { name: /^All / }));
    expect(screen.getByText("Old closed 1")).toBeInTheDocument();
    expect(screen.getByText(/Showing 5 of 5 postings/)).toBeInTheDocument();
  });

  it('"Verified" shows only VERIFIED postings, across all states', async () => {
    const user = userEvent.setup();
    wrap(<PostingsView />);
    await screen.findByText("Open A");
    await user.click(screen.getByRole("button", { name: /^Verified / }));
    expect(screen.getByText("Open A")).toBeInTheDocument();
    expect(screen.getByText("Old closed 3")).toBeInTheDocument(); // verified-but-closed still shown
    expect(screen.queryByText("Open B")).not.toBeInTheDocument();
  });
});

describe("PostingsView — Created column", () => {
  it("shows the formatted lever_created_at, or a dash when absent", async () => {
    api.listRecruitmentPostings.mockResolvedValue([
      posting({ title: "Has Date", lever_created_at: "2026-08-12T00:00:00Z" }),
      posting({ title: "No Date", lever_created_at: null }),
    ]);
    wrap(<PostingsView />);
    await screen.findByText("Has Date");
    expect(screen.getByText("12 Aug 2026")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("PostingsView — four mapping states", () => {
  it("labels auto-verified, manually verified, manually unmapped and unmapped distinctly", async () => {
    api.listRecruitmentPostings.mockResolvedValue([
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
    api.listRecruitmentPostings.mockResolvedValue([
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
    api.listRecruitmentPostings.mockResolvedValue([
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
    api.listRecruitmentPostings.mockResolvedValue([
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
    api.listRecruitmentPostings.mockResolvedValue([
      posting({ id: 504, title: "Fresh Role", mapping_status: "UNMAPPED", mapping_source: "" }),
    ]);
    wrap(<PostingsView />);

    expect(await screen.findByRole("button", { name: "Verify manually" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unmap" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });
});
