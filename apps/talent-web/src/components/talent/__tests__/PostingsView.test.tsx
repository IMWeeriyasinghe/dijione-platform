import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listRecruitmentPostings: vi.fn(),
  listClientPortfolios: vi.fn(),
  verifyPostingMapping: vi.fn(),
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
