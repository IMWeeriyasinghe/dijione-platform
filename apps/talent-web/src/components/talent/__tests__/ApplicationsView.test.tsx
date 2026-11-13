import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listApplicationsPaged: vi.fn(),
  updateApplicationVisibility: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { ApplicationsView } from "../ApplicationsView";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function application(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: Math.floor(Math.random() * 1e6),
    candidate_id: 1,
    candidate_name: "Jane Candidate",
    talent_request_id: 1,
    client_name: "ABC Company",
    designation: "Senior Developer",
    current_stage: "SOURCING",
    status: "ACTIVE",
    score: null,
    recruiter_notes: "",
    client_visible_notes: "",
    rejection_reason: "",
    is_client_visible: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

/** Server-like fake: applies status_filter (incl. the stage=OFFER rule)
 * and returns one page, the way /applications/paged does. */
function serve(rows: ReturnType<typeof application>[]) {
  api.listApplicationsPaged.mockImplementation(
    async ({ status_filter, page, page_size }: { status_filter?: string; page: number; page_size: number }) => {
      const matched = rows.filter(
        (a) =>
          !status_filter ||
          a.status === status_filter ||
          (status_filter === "OFFER" && a.current_stage === "OFFER" && ["ACTIVE", "SHORTLISTED", "CLIENT_REVIEW"].includes(a.status as string)),
      );
      const start = (page - 1) * page_size;
      return {
        items: matched.slice(start, start + page_size),
        total: matched.length,
        page,
        page_size,
        total_pages: Math.max(1, Math.ceil(matched.length / page_size)),
      };
    },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  api.updateApplicationVisibility.mockResolvedValue(application());
});

describe("ApplicationsView — read-only recruitment state", () => {
  it("shows stage and status as read-only labels, not editable controls", async () => {
    serve([application()]);
    wrap(<ApplicationsView />);

    expect(await screen.findByText("Sourcing")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getAllByText("Synced from Lever")).toHaveLength(2);

    // No editable stage/status <select> in the table, and no score
    // <input type=number>. (The page-size selector is pagination, not data.)
    expect(within(screen.getByRole("table")).queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("never renders a Score column or value", async () => {
    serve([application({ score: 8.5 })]);
    wrap(<ApplicationsView />);

    await screen.findByText("Jane Candidate");
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    expect(screen.queryByText("8.5")).not.toBeInTheDocument();
  });

  it("keeps the client-visibility toggle editable and wired to the API", async () => {
    const user = userEvent.setup();
    serve([application({ is_client_visible: false })]);
    wrap(<ApplicationsView />);

    const checkbox = await screen.findByRole("checkbox");
    expect(screen.getByText("Hidden")).toBeInTheDocument();

    await user.click(checkbox);
    expect(api.updateApplicationVisibility).toHaveBeenCalledWith(
      expect.any(Number),
      true
    );
  });
});

describe("ApplicationsView — status click-through filter", () => {
  it("filters to the initial status and shows a clearable chip", async () => {
    const user = userEvent.setup();
    serve([
      application({ candidate_name: "Offer Candidate", status: "OFFER" }),
      application({ candidate_name: "Active Candidate", status: "ACTIVE" }),
    ]);
    wrap(<ApplicationsView initialStatus="OFFER" />);

    expect(await screen.findByText("Offer Candidate")).toBeInTheDocument();
    expect(screen.queryByText("Active Candidate")).not.toBeInTheDocument();
    expect(screen.getByText(/Status: OFFER/)).toBeInTheDocument();

    await user.click(screen.getByText(/Status: OFFER/));
    expect(await screen.findByText("Active Candidate")).toBeInTheDocument();
  });

  it("sends the status filter to the server (Offers in Progress includes Lever stage offers)", async () => {
    serve([
      application({ candidate_name: "Status Offer", status: "OFFER" }),
      application({ candidate_name: "Stage Offer", status: "ACTIVE", current_stage: "OFFER" }),
      application({ candidate_name: "Plain Active", status: "ACTIVE" }),
    ]);
    wrap(<ApplicationsView initialStatus="OFFER" />);
    expect(await screen.findByText("Status Offer")).toBeInTheDocument();
    expect(screen.getByText("Stage Offer")).toBeInTheDocument();
    expect(screen.queryByText("Plain Active")).not.toBeInTheDocument();
    expect(api.listApplicationsPaged).toHaveBeenCalledWith(
      expect.objectContaining({ status_filter: "OFFER", page: 1, page_size: 20 }),
    );
  });

  it("shows every row and no chip when no initial status is given", async () => {
    serve([
      application({ candidate_name: "Offer Candidate", status: "OFFER" }),
      application({ candidate_name: "Active Candidate", status: "ACTIVE" }),
    ]);
    wrap(<ApplicationsView />);

    expect(await screen.findByText("Offer Candidate")).toBeInTheDocument();
    expect(screen.getByText("Active Candidate")).toBeInTheDocument();
    expect(screen.queryByText(/Status:/)).not.toBeInTheDocument();
  });
});

describe("ApplicationsView — server-side pagination", () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) => application({ id: i + 1, candidate_name: `Cand ${i + 1}` }));

  it("defaults to 20 rows with range, total and 20/50/100 sizes", async () => {
    serve(many(57));
    wrap(<ApplicationsView />);
    expect(await screen.findByText("Showing 1–20 of 57 applications")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(20);
    const opts = [...(screen.getByLabelText("Applications per page") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toEqual(["20", "50", "100"]);
  });

  it("pages forward and back to the last page, and size changes reset to page 1", async () => {
    const user = userEvent.setup();
    serve(many(57));
    wrap(<ApplicationsView />);
    await screen.findByText("Showing 1–20 of 57 applications");
    await user.click(screen.getByLabelText("Last page"));
    expect(await screen.findByText("Showing 41–57 of 57 applications")).toBeInTheDocument();
    expect(screen.getByLabelText("Next page")).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Applications per page"), "50");
    expect(await screen.findByText("Showing 1–50 of 57 applications")).toBeInTheDocument();
  });

  it("clearing the status chip returns to page 1 with no filter", async () => {
    const user = userEvent.setup();
    serve(many(45).map((a, i) => ({ ...a, status: i % 2 ? "OFFER" : "ACTIVE" })));
    wrap(<ApplicationsView initialStatus="OFFER" />);
    await screen.findByText("Showing 1–20 of 22 applications");
    await user.click(screen.getByLabelText("Page 2"));
    await screen.findByText("Showing 21–22 of 22 applications");
    await user.click(screen.getByText(/Status: OFFER/));
    expect(await screen.findByText("Showing 1–20 of 45 applications")).toBeInTheDocument();
    expect(api.listApplicationsPaged).toHaveBeenLastCalledWith(
      expect.objectContaining({ status_filter: undefined, page: 1 }),
    );
  });
});
