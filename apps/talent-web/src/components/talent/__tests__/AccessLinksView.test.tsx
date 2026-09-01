import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listClientPortfolios: vi.fn(),
  listMagicLinkGrants: vi.fn(),
  createMagicLinkGrant: vi.fn(),
  revokeMagicLinkGrant: vi.fn(),
  regenerateMagicLinkGrant: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

import { AccessLinksView } from "../AccessLinksView";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const GRANT = {
  public_id: "mlg-abc123",
  client_id: 1,
  client_name: "ABC Company",
  scope_type: "CLIENT_WORKSPACE",
  contact_name: "Priya",
  contact_email: "priya@abc.example",
  token_prefix: "Ab3xTk9p",
  status: "ACTIVE" as const,
  issued_by_user_id: 10,
  issued_at: "2026-09-02T00:00:00Z",
  expires_at: "2026-09-16T00:00:00Z",
  redeemed_at: null,
  last_used_at: null,
  use_count: 0,
  revoked_at: null,
  revoked_by_user_id: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listClientPortfolios.mockResolvedValue([
    { id: 1, name: "ABC Company", industry: null, account_manager: null, status: "ACTIVE", created_at: "", total_requests: 0, active_requests: 0 },
  ]);
  api.listMagicLinkGrants.mockResolvedValue([GRANT]);
});

describe("AccessLinksView", () => {
  it("lists existing grants with the non-secret prefix and status, never a raw token", async () => {
    wrap(<AccessLinksView />);
    expect((await screen.findAllByText("ABC Company")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Ab3xTk9p/)).toBeInTheDocument();
    expect(screen.getByText(/^active$/i)).toBeInTheDocument();
    // The list view must never carry a raw token or the access URL.
    expect(screen.queryByText(/\/access#/)).not.toBeInTheDocument();
  });

  it("shows the one-time access URL after generating, then it can be dismissed", async () => {
    api.createMagicLinkGrant.mockResolvedValue({
      ...GRANT,
      raw_token: "RAW-TOKEN-VALUE",
      access_url: "http://localhost:3100/access#RAW-TOKEN-VALUE",
    });
    const user = userEvent.setup();
    wrap(<AccessLinksView />);

    await screen.findAllByText("ABC Company");
    await user.selectOptions(screen.getByLabelText(/Client/i), "1");
    await user.click(screen.getByRole("button", { name: /Generate access link/i }));

    await waitFor(() =>
      expect(screen.getByText("http://localhost:3100/access#RAW-TOKEN-VALUE")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Shown once/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Dismiss/i }));
    expect(
      screen.queryByText("http://localhost:3100/access#RAW-TOKEN-VALUE"),
    ).not.toBeInTheDocument();
  });

  it("revokes a grant through the API", async () => {
    api.revokeMagicLinkGrant.mockResolvedValue({ ...GRANT, status: "REVOKED" });
    const user = userEvent.setup();
    wrap(<AccessLinksView />);

    await screen.findAllByText("ABC Company");
    await user.click(screen.getByRole("button", { name: /^Revoke$/i }));
    await waitFor(() => expect(api.revokeMagicLinkGrant).toHaveBeenCalledWith("mlg-abc123"));
  });
});
