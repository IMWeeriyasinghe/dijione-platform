import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  ApiError: class extends Error {},
  createApplication: vi.fn(),
  listCandidatesPaged: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import { AddApplicationModal, PICKER_LIMIT } from "../AddApplicationModal";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}
const cand = (id: number, name: string) => ({ id, full_name: name, professional_title: "Engineer" });

beforeEach(() => {
  vi.clearAllMocks();
  api.listCandidatesPaged.mockImplementation(async ({ search, page_size }: { search?: string; page_size: number }) => {
    const all = Array.from({ length: 3000 }, (_, i) => cand(i + 1, `Person ${i + 1}`));
    const m = search ? all.filter((c) => c.full_name.includes(search)) : all;
    return { items: m.slice(0, page_size), total: m.length, page: 1, page_size, total_pages: Math.ceil(m.length / page_size) || 1 };
  });
});

describe("AddApplicationModal — bounded candidate picker", () => {
  it("never loads the whole pool: asks the server for the first 24 and says how many match", async () => {
    wrap(<AddApplicationModal requestId={5} open onClose={() => {}} />);
    expect(await screen.findByText(/Showing the first 24 of 3,000 matches/)).toBeInTheDocument();
    expect(api.listCandidatesPaged).toHaveBeenCalledWith({ search: undefined, page: 1, page_size: PICKER_LIMIT });
    const picker = screen.getByRole("combobox", { name: /^Candidate/ });
    expect(within(picker).getAllByRole("option").filter((o) => (o as HTMLOptionElement).value)).toHaveLength(24);
  });

  it("searches server-side with a debounce", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      wrap(<AddApplicationModal requestId={5} open onClose={() => {}} />);
      await screen.findByText(/Showing the first 24/);
      fireEvent.change(screen.getByLabelText("Find candidate"), { target: { value: "Person 2999" } });
      await act(async () => { vi.advanceTimersByTime(350); });
      await waitFor(() =>
        expect(api.listCandidatesPaged).toHaveBeenLastCalledWith({ search: "Person 2999", page: 1, page_size: 24 }),
      );
      expect(await screen.findByRole("option", { name: /Person 2999/ })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not query while closed", () => {
    wrap(<AddApplicationModal requestId={5} open={false} onClose={() => {}} />);
    expect(api.listCandidatesPaged).not.toHaveBeenCalled();
  });
});
