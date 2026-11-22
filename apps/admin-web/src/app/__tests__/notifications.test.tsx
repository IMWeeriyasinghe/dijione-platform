import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Admin > Notifications: recipient picker, filters, statuses, summary, details and permissions.
const perms = vi.hoisted(() => ({ set: new Set<string>() }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  usePlatformPermission: (p: string) => perms.set.has(p),
  useAuthorizedImage: () => null,
}));
const api = vi.hoisted(() => ({
  getNotificationSummary: vi.fn(),
  listEmailOutbox: vi.fn(),
  getEmailOutboxItem: vi.fn(),
  retryEmailOutboxItem: vi.fn(),
  dispatchNotificationsNow: vi.fn(),
  listNotificationEvents: vi.fn(),
  setNotificationEvent: vi.fn(),
  listEmailTestRecipients: vi.fn(),
  addEmailTestRecipient: vi.fn(),
  removeEmailTestRecipient: vi.fn(),
  searchNotificationRecipients: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ApiError } from "@/lib/api";
import Page from "../notifications/page";

const MANAGE = "platform.admin.manage_notifications";
const STATUSES = ["PENDING", "SENDING", "RETRY", "SUBMITTED", "SIMULATED", "FAILED", "BLOCKED", "DISABLED",
  "SUPERSEDED", "SKIPPED"];
const SUMMARY = {
  counts: { PENDING: 1, SENDING: 1, RETRY: 2, SUBMITTED: 7, SIMULATED: 3, FAILED: 4, BLOCKED: 5, DISABLED: 0,
    SUPERSEDED: 0, SKIPPED: 0 },
  environment: "dev", transport: "graph", configured_policy: "internal_allowlist", effective_policy: "internal_allowlist",
  is_production: false, sender_mailbox: "appassistant@dijitalteam.com", access_notifications_enabled: true,
  dispatcher_enabled: true, applications: [{ key: "dijione", name: "DijiOne" }], statuses: STATUSES,
};
const EVENTS = [
  { event_type: "access.welcome", application_key: "dijione", subject: "[DijiOne] | Access Available", description: "", enabled: true },
  { event_type: "access.granted", application_key: "dijione", subject: "[DijiOne] | Access Granted", description: "", enabled: true },
];
const row = (id: number, extra: Record<string, unknown> = {}) => ({
  id, correlation_id: `c-${id}`, application_key: "dijione", application_name: "DijiOne", event_type: "access.granted",
  recipient_email: `person${id}@dijitalteam.com`, recipient_user_id: id, subject: "[DijiOne] | Access Granted",
  status: "SUBMITTED", attempts: 1, max_attempts: 5, transport_outcome: "SUBMITTED", created_at: "2026-11-22T07:07:17Z",
  not_before: "2026-11-22T07:08:17Z", last_attempt_at: "2026-11-22T07:08:27Z", completed_at: "2026-11-22T07:08:27Z",
  can_retry: false, ...extra,
});
const MAD = { source: "user", user_id: 14, full_name: "Madushanka Weeriyasinghe", email: "madushanka@dijitalteam.com",
  employee_number: "10042", is_active: true, has_photo: false };
const OLD = { source: "history", user_id: null, full_name: null, email: "old.svc@dijitalteam.com", employee_number: null,
  is_active: null, has_photo: false };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}
const lastFilters = () => api.listEmailOutbox.mock.calls.at(-1)?.[0];
const recipientBox = () => screen.getByLabelText("Recipient");
async function type(text: string) {
  fireEvent.change(recipientBox(), { target: { value: text } });
  await act(() => new Promise((r) => setTimeout(r, 350))); // debounce
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  perms.set = new Set([MANAGE]);
  api.getNotificationSummary.mockResolvedValue(SUMMARY);
  api.listNotificationEvents.mockResolvedValue(EVENTS);
  api.listEmailOutbox.mockResolvedValue({ total: 1, items: [row(1)] });
  api.searchNotificationRecipients.mockResolvedValue([MAD, OLD]);
});

describe("recipient picker", () => {
  it("suggests DijiOne users and history-only addresses, and filters by the selected email", async () => {
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    await type("mad");
    expect(api.searchNotificationRecipients).toHaveBeenCalledWith("mad", expect.anything());
    const list = await screen.findByRole("listbox");
    expect(within(list).getByText("Madushanka Weeriyasinghe")).toBeInTheDocument();
    expect(within(list).getByText("madushanka@dijitalteam.com")).toBeInTheDocument();
    expect(within(list).getByText("History")).toBeInTheDocument();
    fireEvent.mouseDown(within(list).getByText("Madushanka Weeriyasinghe"));
    await waitFor(() => expect(lastFilters()).toMatchObject({ recipient: "madushanka@dijitalteam.com", offset: 0 }));
  });

  it("supports keyboard selection", async () => {
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    await type("old");
    await screen.findByText("old.svc@dijitalteam.com");
    fireEvent.keyDown(recipientBox(), { key: "ArrowDown" }); // second suggestion (history)
    fireEvent.keyDown(recipientBox(), { key: "Enter" });
    await waitFor(() => expect(lastFilters()).toMatchObject({ recipient: "old.svc@dijitalteam.com" }));
  });

  it("searches history for a manually typed address without a directory match", async () => {
    api.searchNotificationRecipients.mockResolvedValue([]);
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    await type("gone.person@");
    expect(await screen.findByText("No matching people.")).toBeInTheDocument();
    fireEvent.keyDown(recipientBox(), { key: "Enter" });
    await waitFor(() => expect(lastFilters()).toMatchObject({ recipient: "gone.person@" }));
  });

  it("clears the selected recipient", async () => {
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    fireEvent.change(recipientBox(), { target: { value: "x@y" } });
    fireEvent.keyDown(recipientBox(), { key: "Enter" });
    await waitFor(() => expect(lastFilters()).toMatchObject({ recipient: "x@y" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear recipient" }));
    await waitFor(() => expect(lastFilters()?.recipient).toBeUndefined());
    expect(recipientBox()).toHaveValue("");
  });

  it("does not search below two characters, shows search errors, and never sends or allowlists", async () => {
    api.searchNotificationRecipients.mockRejectedValue(new ApiError(500, "boom"));
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    await type("m");
    expect(api.searchNotificationRecipients).not.toHaveBeenCalled();
    await type("ma");
    expect(await screen.findByText("Could not search people.")).toBeInTheDocument();
    expect(api.addEmailTestRecipient).not.toHaveBeenCalled();
    expect(api.dispatchNotificationsNow).not.toHaveBeenCalled();
    expect(api.retryEmailOutboxItem).not.toHaveBeenCalled();
  });

  it("only shows results for the latest query", async () => {
    let resolveSlow: (v: unknown) => void = () => {};
    api.searchNotificationRecipients.mockImplementation((q: string) =>
      q === "ma" ? new Promise((r) => { resolveSlow = r; }) : Promise.resolve([OLD]));
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    await type("ma");
    await type("old");
    await screen.findByText("old.svc@dijitalteam.com");
    await act(async () => resolveSlow([MAD]));
    expect(screen.queryByText("Madushanka Weeriyasinghe")).not.toBeInTheDocument();
  });
});

describe("filters, pagination and empty states", () => {
  it("combines filters, resets them and shows a filtered empty state", async () => {
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    fireEvent.change(screen.getByLabelText("Event"), { target: { value: "access.welcome" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "FAILED" } });
    await waitFor(() => expect(lastFilters()).toMatchObject({ event_type: "access.welcome", status: "FAILED", offset: 0 }));
    api.listEmailOutbox.mockResolvedValue({ total: 0, items: [] });
    fireEvent.change(screen.getByLabelText("Application"), { target: { value: "dijione" } });
    expect(await screen.findByText("No notifications match these filters")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Reset filters" })[0]);
    await waitFor(() => expect(lastFilters()).toEqual({ limit: 50, offset: 0 }));
  });

  it("takes event options from the events API", async () => {
    renderPage();
    const select = await screen.findByLabelText("Event");
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
  });

  it("pages through history", async () => {
    api.listEmailOutbox.mockResolvedValue({ total: 120, items: [row(1)] });
    renderPage();
    expect(await screen.findByText("1–50 of 120")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastFilters()).toMatchObject({ offset: 50 }));
  });

  it("shows a load error", async () => {
    api.listEmailOutbox.mockRejectedValue(new ApiError(500, "Server error"));
    renderPage();
    expect(await screen.findByText("Server error")).toBeInTheDocument();
  });
});

describe("statuses, summary and details", () => {
  it("labels statuses clearly and never as delivered", async () => {
    api.listEmailOutbox.mockResolvedValue({ total: 2, items: [row(1), row(2, { status: "SIMULATED" })] });
    renderPage();
    const submitted = await screen.findByText("Submitted", { selector: "span" });
    expect(submitted).toHaveAttribute("title", expect.stringMatching(/not a delivery confirmation/i));
    expect(screen.getByText("Simulated", { selector: "span" })).toHaveAttribute(
      "title", expect.stringMatching(/without sending a real email/i));
    expect(screen.queryByText(/delivered/i)).not.toBeInTheDocument();
  });

  it("summarises all-history counts", async () => {
    renderPage();
    const strip = await screen.findByRole("region", { name: /delivery summary/i });
    const value = (label: string) => within(strip).getByText(label).nextElementSibling?.textContent;
    expect(value("Submitted")).toBe("7");
    expect(value("Pending / Retry")).toBe("4");
    expect(value("Failed")).toBe("4");
    expect(value("Blocked")).toBe("5");
    expect(within(strip).getByText(/all history/i)).toBeInTheDocument();
  });

  it("shows notification details", async () => {
    api.getEmailOutboxItem.mockResolvedValue({ ...row(1), last_error: null, graph_request_id: "g-1" });
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    const dialog = (await screen.findByText("Email details")).closest("div.relative") as HTMLElement;
    await within(dialog).findByText("Correlation ID");
    for (const label of ["Application", "Subject", "Recipient", "Event", "Status", "Attempts", "Queued", "Scheduled for",
      "Processed", "Transport result", "Correlation ID", "Graph request ID"]) {
      expect(within(dialog).getByText(label)).toBeInTheDocument();
    }
    expect(within(dialog).getByText("g-1")).toBeInTheDocument();
  });
});

describe("permissions", () => {
  it("hides management actions without manage_notifications", async () => {
    perms.set = new Set();
    api.listEmailOutbox.mockResolvedValue({ total: 1, items: [row(1, { status: "FAILED", can_retry: true })] });
    api.getEmailOutboxItem.mockResolvedValue({ ...row(1, { status: "FAILED", can_retry: true }), last_error: "x" });
    renderPage();
    await screen.findByText("person1@dijitalteam.com");
    expect(screen.queryByRole("button", { name: /process now/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    await screen.findByText("Correlation ID");
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("explains a read-only View-as session", async () => {
    api.getNotificationSummary.mockRejectedValue(new ApiError(403, "This is a read-only View-as session"));
    renderPage();
    expect(await screen.findByText("Not available in a read-only View-as session.")).toBeInTheDocument();
  });
});
