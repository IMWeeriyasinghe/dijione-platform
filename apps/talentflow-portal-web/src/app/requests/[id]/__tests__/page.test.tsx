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

const params = vi.hoisted(() => ({ value: { id: "7" } }));
vi.mock("next/navigation", () => ({
  useParams: () => params.value,
}));

const api = vi.hoisted(() => ({
  getRequest: vi.fn(),
  listRequestCandidates: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import RequestDetailPage from "../page";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function request(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 7,
    request_code: "TA-0007",
    designation: "Senior Developer",
    current_stage: "INTERVIEWS",
    client_safe_status_text: "In interviews",
    progress_percent: 60,
    stage_timeline: [],
    location: "",
    ...over,
  };
}

function candidate(over: Partial<Record<string, unknown>> = {}) {
  return {
    application_id: 99,
    full_name: "Jane Candidate",
    professional_title: "Senior Developer",
    skills: [],
    relevant_experience_summary: "",
    current_stage: "INTERVIEWS",
    upcoming_interview_status: null,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getRequest.mockResolvedValue(request());
  api.listRequestCandidates.mockResolvedValue([candidate()]);
});

describe("RequestDetailPage — candidate cards link to Candidate Review Detail", () => {
  it("each shared-candidate card links to /candidates/{applicationId}", async () => {
    wrap(<RequestDetailPage />);

    const card = await screen.findByText("Jane Candidate");
    expect(card.closest("a")).toHaveAttribute("href", "/candidates/99");
  });

  it("shows the shared-candidate count in the section heading", async () => {
    api.listRequestCandidates.mockResolvedValue([candidate(), candidate({ application_id: 100 })]);
    wrap(<RequestDetailPage />);

    expect(await screen.findByText("Candidates shared with you (2)")).toBeInTheDocument();
  });
});
