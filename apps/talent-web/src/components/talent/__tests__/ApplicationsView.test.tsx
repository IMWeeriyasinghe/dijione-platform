import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listApplications: vi.fn(),
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

beforeEach(() => {
  vi.clearAllMocks();
  api.updateApplicationVisibility.mockResolvedValue(application());
});

describe("ApplicationsView — read-only recruitment state", () => {
  it("shows stage and status as read-only labels, not editable controls", async () => {
    api.listApplications.mockResolvedValue([application()]);
    wrap(<ApplicationsView />);

    expect(await screen.findByText("Sourcing")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getAllByText("Synced from Lever")).toHaveLength(2);

    // No editable stage/status <select>, and no score <input type=number>.
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("never renders a Score column or value", async () => {
    api.listApplications.mockResolvedValue([application({ score: 8.5 })]);
    wrap(<ApplicationsView />);

    await screen.findByText("Jane Candidate");
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    expect(screen.queryByText("8.5")).not.toBeInTheDocument();
  });

  it("keeps the client-visibility toggle editable and wired to the API", async () => {
    const user = userEvent.setup();
    api.listApplications.mockResolvedValue([application({ is_client_visible: false })]);
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
    api.listApplications.mockResolvedValue([
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

  it("shows every row and no chip when no initial status is given", async () => {
    api.listApplications.mockResolvedValue([
      application({ candidate_name: "Offer Candidate", status: "OFFER" }),
      application({ candidate_name: "Active Candidate", status: "ACTIVE" }),
    ]);
    wrap(<ApplicationsView />);

    expect(await screen.findByText("Offer Candidate")).toBeInTheDocument();
    expect(screen.getByText("Active Candidate")).toBeInTheDocument();
    expect(screen.queryByText(/Status:/)).not.toBeInTheDocument();
  });
});
