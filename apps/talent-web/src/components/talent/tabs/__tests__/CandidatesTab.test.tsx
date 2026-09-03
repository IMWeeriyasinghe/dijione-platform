import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listApplications: vi.fn(),
  listRequestCandidates: vi.fn(),
  updateApplicationVisibility: vi.fn(),
  listCandidates: vi.fn(),
  createApplication: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { StaffCandidatesTab } from "../CandidatesTab";

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
    current_stage: "INTERVIEWS",
    status: "SHORTLISTED",
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

describe("StaffCandidatesTab — read-only recruitment state", () => {
  it("shows stage and status as read-only labels with no editable controls or Score column", async () => {
    api.listApplications.mockResolvedValue([application({ score: 9 })]);
    wrap(<StaffCandidatesTab requestId={1} />);

    expect(await screen.findByText("Interviews")).toBeInTheDocument();
    expect(screen.getByText("Shortlisted")).toBeInTheDocument();
    expect(screen.getAllByText("Synced from Lever")).toHaveLength(2);
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
    expect(screen.queryByText("9")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("keeps the client-visibility toggle editable", async () => {
    const user = userEvent.setup();
    api.listApplications.mockResolvedValue([application({ is_client_visible: false })]);
    wrap(<StaffCandidatesTab requestId={1} />);

    const checkbox = await screen.findByRole("checkbox");
    await user.click(checkbox);
    expect(api.updateApplicationVisibility).toHaveBeenCalledWith(expect.any(Number), true);
  });
});
