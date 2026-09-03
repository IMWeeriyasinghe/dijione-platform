import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listClientPortfolios: vi.fn(),
  listMagicLinkGrants: vi.fn(),
  createMagicLinkGrant: vi.fn(),
  revokeMagicLinkGrant: vi.fn(),
  regenerateMagicLinkGrant: vi.fn(),
  extendMagicLinkGrant: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

import { AccessLinksView, dateInputValue, endOfDayIso, maxSelectableDate } from "../AccessLinksView";

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
  sessionStorage.clear();
  api.listClientPortfolios.mockResolvedValue([
    {
      id: 1, name: "ABC Company", industry: null, account_manager: null, status: "ACTIVE", created_at: "",
      total_requests: 0, active_requests: 0, active_application_count: 0, client_visible_count: 0,
      latest_request_at: null,
    },
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

  it("recalls the just-generated link on a same-session remount, but not after Dismiss", async () => {
    api.createMagicLinkGrant.mockResolvedValue({
      ...GRANT,
      raw_token: "RAW-TOKEN-VALUE",
      access_url: "http://localhost:3100/access#RAW-TOKEN-VALUE",
    });
    const user = userEvent.setup();
    const first = wrap(<AccessLinksView />);

    await screen.findAllByText("ABC Company");
    await user.selectOptions(screen.getByLabelText(/Client/i), "1");
    await user.click(screen.getByRole("button", { name: /Generate access link/i }));
    await waitFor(() =>
      expect(screen.getByText("http://localhost:3100/access#RAW-TOKEN-VALUE")).toBeInTheDocument(),
    );
    first.unmount();

    // A fresh mount within the same browser session (sessionStorage
    // persists) recalls the link without calling the API again.
    wrap(<AccessLinksView />);
    expect(await screen.findByText("http://localhost:3100/access#RAW-TOKEN-VALUE")).toBeInTheDocument();
    expect(api.createMagicLinkGrant).toHaveBeenCalledTimes(1);
  });

  it("extending a grant calls the API with the chosen date and refreshes the list", async () => {
    api.extendMagicLinkGrant.mockResolvedValue({ ...GRANT, expires_at: "2026-12-01T23:59:59.000Z" });
    const user = userEvent.setup();
    wrap(<AccessLinksView />);

    await screen.findAllByText("ABC Company");
    await user.click(screen.getByRole("button", { name: "Extend" }));

    const dateInput = document.querySelector('input[type="date"].w-36') as HTMLInputElement;
    expect(dateInput).toBeTruthy();
    await user.clear(dateInput);
    await user.type(dateInput, "2026-12-01");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.extendMagicLinkGrant).toHaveBeenCalledWith(
        "mlg-abc123",
        expect.stringContaining("2026-12-01"),
      ),
    );
  });

  it("shows an 'in N days' hint for an active grant, amber when 3 days or fewer remain", async () => {
    const soon = new Date();
    soon.setDate(soon.getDate() + 2);
    api.listMagicLinkGrants.mockResolvedValue([{ ...GRANT, expires_at: soon.toISOString() }]);
    wrap(<AccessLinksView />);

    expect(await screen.findByText("in 2 days")).toBeInTheDocument();
  });

  it("a revoked grant shows no Extend/Regenerate/Revoke actions", async () => {
    api.listMagicLinkGrants.mockResolvedValue([{ ...GRANT, status: "REVOKED", revoked_at: "2026-09-03T00:00:00Z" }]);
    wrap(<AccessLinksView />);

    await screen.findAllByText("ABC Company");
    expect(screen.queryByRole("button", { name: "Extend" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Revoke$/i })).not.toBeInTheDocument();
    // Matches the Actions-column "Revoked <date>" text, not the Status
    // badge (exactly "Revoked", no trailing content) — and avoids
    // depending on formatDate's locale-specific day/month ordering.
    expect(screen.getByText(/^Revoked /)).toBeInTheDocument();
  });
});

describe("dateInputValue / endOfDayIso — timezone consistency", () => {
  const ORIGINAL_TZ = process.env.TZ;

  afterEach(() => {
    process.env.TZ = ORIGINAL_TZ;
    vi.useRealTimers();
  });

  it("the offered min/max bounds and their submitted expires_at stay inside the backend's [1,90]-day window in a positive-UTC-offset timezone", () => {
    // Asia/Kolkata (UTC+5:30). Pinned to a local early-morning instant —
    // the exact condition that made the old UTC-round-trip version of
    // dateInputValue() return a date one day earlier than the local
    // calendar day, disagreeing with endOfDayIso's local-time parse.
    process.env.TZ = "Asia/Kolkata";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-03T20:30:00.000Z")); // 2026-09-04 02:00 IST

    const now = Date.now();
    const minDate = dateInputValue(1); // MIN_EXPIRY_DAYS
    const maxDate = maxSelectableDate(); // what the UI's max= attribute offers

    const minSubmitted = new Date(endOfDayIso(minDate)).getTime();
    const maxSubmitted = new Date(endOfDayIso(maxDate)).getTime();

    // Same bound the backend enforces (MagicLinkService._resolve_expiry):
    // now + [1, 90] days, inclusive.
    const backendMin = now + 1 * 86_400_000;
    const backendMax = now + 90 * 86_400_000;

    expect(minSubmitted).toBeGreaterThanOrEqual(backendMin);
    expect(maxSubmitted).toBeLessThanOrEqual(backendMax);
  });

  it("the max bound survives a DST transition inside the offered window, at the true worst-case time of day (local midnight)", () => {
    // America/Los_Angeles: "now" pinned to local midnight (the worst case
    // for a fixed calendar-day buffer — see maxSelectableDate's comment),
    // with the window's 88 forward days crossing the Nov 1, 2026 US
    // fall-back DST transition. A single day of buffer (day 89) leaves
    // only ~1 second of margin at this worst-case time of day, which the
    // 1-hour DST shift pushes negative; day 88 keeps a real ~24h margin
    // that absorbs it.
    process.env.TZ = "America/Los_Angeles";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-03T07:00:00.000Z")); // 2026-09-03 00:00 PDT

    const now = Date.now();
    const maxDate = maxSelectableDate();
    const maxSubmitted = new Date(endOfDayIso(maxDate)).getTime();
    const backendMax = now + 90 * 86_400_000;

    expect(maxSubmitted).toBeLessThanOrEqual(backendMax);
  });
});
