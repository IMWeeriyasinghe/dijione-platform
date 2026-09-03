import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const params = vi.hoisted(() => ({ value: { applicationId: "42" } }));
vi.mock("next/navigation", () => ({
  useParams: () => params.value,
}));

const api = vi.hoisted(() => ({
  getCandidateReview: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));
vi.mock("@/lib/api", () => api);

import CandidateReviewPage from "../page";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function candidate(over: Partial<Record<string, unknown>> = {}) {
  return {
    application_id: 42,
    full_name: "Jane Candidate",
    professional_title: "Senior Developer",
    skills: ["Python", "SQL"],
    relevant_experience_summary: "8 years building backend systems.",
    current_stage: "INTERVIEWS",
    upcoming_interview_status: "SCHEDULED",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  params.value = { applicationId: "42" };
});

describe("CandidateReviewPage", () => {
  it("renders the client-safe candidate detail", async () => {
    api.getCandidateReview.mockResolvedValue(candidate());
    wrap(<CandidateReviewPage />);

    expect(await screen.findByText("Jane Candidate")).toBeInTheDocument();
    expect(screen.getByText("Senior Developer")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("8 years building backend systems.")).toBeInTheDocument();
    expect(screen.getByText("SCHEDULED")).toBeInTheDocument();
  });

  it("omits the skills and interview sections when empty", async () => {
    api.getCandidateReview.mockResolvedValue(
      candidate({ skills: [], relevant_experience_summary: "", upcoming_interview_status: null })
    );
    wrap(<CandidateReviewPage />);

    await screen.findByText("Jane Candidate");
    expect(screen.queryByText("Upcoming interview")).not.toBeInTheDocument();
  });

  it("shows a generic not-found state on any fetch failure — never distinguishes why", async () => {
    api.getCandidateReview.mockRejectedValue(new api.ApiError(404, "Not found"));
    wrap(<CandidateReviewPage />);

    expect(await screen.findByText("Candidate not found")).toBeInTheDocument();
    expect(
      screen.getByText(/no longer shared with you, or the link is no longer valid/i)
    ).toBeInTheDocument();
    // No hint of the real reason (cross-client, not-visible, or truly
    // nonexistent) ever reaches the UI.
    expect(screen.queryByText(/client/i)).not.toBeInTheDocument();
  });

  it("shows a retryable error state (not the fail-closed not-found message) for a server error", async () => {
    api.getCandidateReview.mockRejectedValue(new api.ApiError(500, "Server error"));
    wrap(<CandidateReviewPage />);

    await screen.findByRole("button", { name: /retry|try again/i });
    expect(screen.queryByText("Candidate not found")).not.toBeInTheDocument();
  });
});
