import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  CANDIDATE_PAGE_SIZES: [12, 24, 48, 96] as const,
  listCandidatesPaged: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { CandidatePoolView } from "../CandidatePoolView";
import { pageWindow } from "../TalentPagination";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function candidate(id: number) {
  return {
    id, full_name: `Candidate ${id}`, email: "", phone: "", professional_title: "Engineer",
    summary: "", location: "", availability_status: "IN_PROCESS", skills: [], cv_reference: "",
    source: "LEVER", applications: [], created_at: "2026-01-01T00:00:00Z",
  };
}

function pageOf(total: number, page: number, page_size: number) {
  const start = (page - 1) * page_size;
  const n = Math.max(0, Math.min(page_size, total - start));
  return {
    items: Array.from({ length: n }, (_, i) => candidate(start + i + 1)),
    total, page, page_size, total_pages: Math.max(1, Math.ceil(total / page_size)),
  };
}

const lastCall = () => api.listCandidatesPaged.mock.calls.at(-1)![0];

describe("CandidatePoolView", () => {
  beforeEach(() => {
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
    api.listCandidatesPaged.mockReset();
    api.listCandidatesPaged.mockImplementation(async ({ page, page_size }) => pageOf(245, page, page_size));
  });

  it("shows the cleaned-up description with no developer references", async () => {
    wrap(<CandidatePoolView />);
    expect(
      screen.getByText("One master candidate profile, sourced from Lever and reusable across multiple client engagements.")
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/CLAUDE\.md|§/);
  });

  it("requests page 1 with a default page size of 12 and shows range + total", async () => {
    wrap(<CandidatePoolView />);
    expect(await screen.findByText("Showing 1–12 of 245 candidates")).toBeInTheDocument();
    expect(lastCall()).toEqual({ search: undefined, page: 1, page_size: 12 });
    expect(screen.getAllByText(/^Candidate \d+$/)).toHaveLength(12);
  });

  it("navigates with numbered, next, last, first; marks active page and disables invalid controls", async () => {
    const user = userEvent.setup();
    wrap(<CandidatePoolView />);
    await screen.findByText("Showing 1–12 of 245 candidates");
    expect(screen.getByLabelText("First page")).toBeDisabled();
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
    expect(screen.getByLabelText("Page 1")).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByLabelText("Page 2"));
    await screen.findByText("Showing 13–24 of 245 candidates");
    expect(screen.getByLabelText("Page 2")).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByLabelText("Next page"));
    await screen.findByText("Showing 25–36 of 245 candidates");

    await user.click(screen.getByLabelText("Last page"));
    await screen.findByText("Showing 241–245 of 245 candidates");
    expect(screen.getByLabelText("Next page")).toBeDisabled();
    expect(screen.getByLabelText("Last page")).toBeDisabled();

    await user.click(screen.getByLabelText("First page"));
    await screen.findByText("Showing 1–12 of 245 candidates");
  });

  it.each([24, 48, 96])("changing page size to %i resets to page 1", async (size) => {
    const user = userEvent.setup();
    wrap(<CandidatePoolView />);
    await screen.findByText("Showing 1–12 of 245 candidates");
    await user.click(screen.getByLabelText("Page 2"));
    await screen.findByText("Showing 13–24 of 245 candidates");
    await user.click(screen.getByLabelText("Page 3"));
    await screen.findByText("Showing 25–36 of 245 candidates");
    await user.selectOptions(screen.getByLabelText("Candidates per page"), String(size));
    await waitFor(() => expect(lastCall()).toEqual({ search: undefined, page: 1, page_size: size }));
  });

  it("debounces search, sends it server-side, resets to page 1 and keeps page size", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      wrap(<CandidatePoolView />);
      await screen.findByText("Showing 1–12 of 245 candidates");
      fireEvent.change(screen.getByLabelText("Candidates per page"), { target: { value: "24" } });
      await waitFor(() => expect(lastCall().page_size).toBe(24));
      fireEvent.click(screen.getByLabelText("Page 2"));
      await waitFor(() => expect(lastCall().page).toBe(2));
      const before = api.listCandidatesPaged.mock.calls.length;

      const input = screen.getByLabelText("Search candidates");
      fireEvent.change(input, { target: { value: "py" } });
      fireEvent.change(input, { target: { value: "pyth" } });
      fireEvent.change(input, { target: { value: "python" } });
      expect(api.listCandidatesPaged.mock.calls.length).toBe(before); // nothing yet
      await act(async () => { vi.advanceTimersByTime(350); });
      await waitFor(() => expect(lastCall()).toEqual({ search: "python", page: 1, page_size: 24 }));
      const searchCalls = api.listCandidatesPaged.mock.calls.slice(before).filter((c) => c[0].search);
      expect(searchCalls).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("never shows the previous search's results while a new search loads", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let release!: () => void;
      wrap(<CandidatePoolView />);
      await screen.findByText("Showing 1–12 of 245 candidates");
      api.listCandidatesPaged.mockImplementation(
        ({ page, page_size }) =>
          new Promise((resolve) => { release = () => resolve(pageOf(3, page, page_size)); })
      );
      fireEvent.change(screen.getByLabelText("Search candidates"), { target: { value: "zed" } });
      await act(async () => { vi.advanceTimersByTime(350); });
      await waitFor(() => expect(lastCall().search).toBe("zed"));
      expect(screen.queryByText("Showing 1–12 of 245 candidates")).not.toBeInTheDocument();
      expect(screen.getByText("Loading candidates…")).toBeInTheDocument();
      await act(async () => { release(); });
      expect(await screen.findByText("Showing 1–3 of 3 candidates")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers exactly 12/24/48/96 per page", async () => {
    wrap(<CandidatePoolView />);
    await screen.findByText("Showing 1–12 of 245 candidates");
    const opts = [...(screen.getByLabelText("Candidates per page") as HTMLSelectElement).options].map((o) => o.value);
    expect(opts).toEqual(["12", "24", "48", "96"]);
  });

  it("lays a full default page out as complete rows of the 3/2-column grid", async () => {
    wrap(<CandidatePoolView />);
    await screen.findByText("Showing 1–12 of 245 candidates");
    const grid = screen.getAllByText(/^Candidate \d+$/)[0].closest("div.grid") as HTMLElement;
    expect(grid.className).toMatch(/sm:grid-cols-2/);
    expect(grid.className).toMatch(/lg:grid-cols-3/);
    expect(grid.children).toHaveLength(12); // 4 rows x 3 desktop, 6 rows x 2 tablet
  });

  it("highlights the active page with the orange ring and dark bold text, never white text", async () => {
    const user = userEvent.setup();
    wrap(<CandidatePoolView />);
    await screen.findByText("Showing 1–12 of 245 candidates");
    await user.click(screen.getByLabelText("Page 2"));
    await screen.findByText("Showing 13–24 of 245 candidates");
    const current = screen.getByLabelText("Page 2");
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current.className).toMatch(/ring-dt-orange/);
    expect(current.className).toMatch(/font-bold/);
    expect(current.className).toMatch(/text-dt-text-primary/);
    expect(current.className).not.toMatch(/text-white|bg-dt-surface\b/);
    expect(screen.getByLabelText("Page 1")).not.toHaveAttribute("aria-current");
    expect(screen.getByLabelText("Page 1").className).not.toMatch(/ring-dt-orange/);
  });

  it("shows an empty state for a search with no matches", async () => {
    api.listCandidatesPaged.mockImplementation(async ({ page, page_size }) => pageOf(0, page, page_size));
    wrap(<CandidatePoolView />);
    expect(await screen.findByText("No candidates found")).toBeInTheDocument();
    expect(screen.queryByLabelText("Candidate pagination")).not.toBeInTheDocument();
  });

  it("shows the error state with retry when the request fails", async () => {
    api.listCandidatesPaged.mockRejectedValueOnce(new Error("boom"));
    const user = userEvent.setup();
    wrap(<CandidatePoolView />);
    const retry = await screen.findByRole("button", { name: /try again|retry/i });
    await user.click(retry);
    expect(await screen.findByText("Showing 1–12 of 245 candidates")).toBeInTheDocument();
  });
});

describe("pageWindow", () => {
  it("lists all pages when few", () => expect(pageWindow(2, 5)).toEqual([1, 2, 3, 4, 5]));
  it("compresses large ranges with gaps", () => {
    expect(pageWindow(1, 25)).toEqual([1, 2, "gap", 25]);
    expect(pageWindow(12, 25)).toEqual([1, "gap", 11, 12, 13, "gap", 25]);
    expect(pageWindow(25, 25)).toEqual([1, "gap", 24, 25]);
  });
});
