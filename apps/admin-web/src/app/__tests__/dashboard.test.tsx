import { act, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Admin Center dashboard: one bounded request, an explained wait, retry on timeout/5xx, no retry on refusal.
const api = vi.hoisted(() => ({ getAdminDashboard: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ApiError } from "@/lib/api";
import Page from "../page";

const COUNTS = {
  total_users: 3, active_users: 3, super_admins: 1, platform_admins: 0, active_modules: 5,
  pending_talent_requests: 2,
};

function renderPage() {
  // The page sets its own retry policy; the client default must not override it.
  const client = new QueryClient();
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}

/** Never resolves on its own; rejects like fetch does when its signal aborts. */
function hangUntilAborted(signal?: AbortSignal) {
  return new Promise((_resolve, reject) => {
    signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  api.getAdminDashboard.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("Admin dashboard loading", () => {
  it("renders the counts from a single request", async () => {
    api.getAdminDashboard.mockResolvedValue(COUNTS);
    renderPage();
    await advance(0);
    expect(screen.getByText("Total Users")).toBeInTheDocument();
    expect(screen.getByText("Talent Requests Pending Review")).toBeInTheDocument();
    expect(api.getAdminDashboard).toHaveBeenCalledTimes(1);
    expect(api.getAdminDashboard.mock.calls[0][0]).toBeInstanceOf(AbortSignal);
  });

  it("explains a slow response instead of spinning silently", async () => {
    api.getAdminDashboard.mockImplementation(hangUntilAborted);
    renderPage();
    await advance(0);
    expect(screen.getByText("Loading admin dashboard…")).toBeInTheDocument();
    await advance(5_000);
    expect(screen.getByText(/taking longer than usual/i)).toBeInTheDocument();
  });

  it("abandons an attempt after 20 s and retries, then succeeds", async () => {
    api.getAdminDashboard.mockImplementationOnce(hangUntilAborted).mockResolvedValue(COUNTS);
    renderPage();
    await advance(19_000);
    expect(api.getAdminDashboard).toHaveBeenCalledTimes(1);
    await advance(1_100); // attempt 1 aborted at 20 s
    expect(screen.getByText(/trying again/i)).toBeInTheDocument();
    await advance(1_000); // retry delay
    expect(api.getAdminDashboard).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Total Users")).toBeInTheDocument();
  });

  it("stops after two retries and offers a manual retry", async () => {
    api.getAdminDashboard.mockRejectedValue(new ApiError(500, "Internal Server Error"));
    renderPage();
    await advance(5_000);
    expect(api.getAdminDashboard).toHaveBeenCalledTimes(3);
    expect(screen.getByText(/did not respond/i)).toBeInTheDocument();

    api.getAdminDashboard.mockResolvedValue(COUNTS);
    fireEvent.click(screen.getByRole("button", { name: /retry|try again/i }));
    await advance(0);
    expect(screen.getByText("Total Users")).toBeInTheDocument();
  });

  it("does not retry a refusal", async () => {
    api.getAdminDashboard.mockRejectedValue(new ApiError(403, "Platform admin access required"));
    renderPage();
    await advance(5_000);
    expect(api.getAdminDashboard).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Platform admin access required/)).toBeInTheDocument();
  });
});
