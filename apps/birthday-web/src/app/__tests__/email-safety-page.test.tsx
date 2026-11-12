import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Round 6 — Email Safety admin page (DijiBirthday-owned non-production
// outbound-recipient allowlist, docs/platform/email-architecture.md). The
// backend independently 404s every route in PROD (require_non_production())
// — this page's own scope?.isAdmin gate is UI convenience only, tested
// separately from that server-side guarantee.

let isAdmin = true;
vi.mock("@dijione/auth-client", () => ({
  useBirthdayScope: () => ({ isAdmin }),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    Button: ({ children, loading, ...props }: any) => (
      <button {...props} data-loading={loading ? "true" : "false"}>
        {children}
      </button>
    ),
    EmptyState: ({ title, description }: any) => (
      <div data-testid="empty-state">
        <p>{title}</p>
        {description && <p>{description}</p>}
      </div>
    ),
    ErrorState: ({ onRetry }: any) => (
      <div>
        <p>error</p>
        <button onClick={onRetry}>retry</button>
      </div>
    ),
    FormField: ({ label, children }: any) => (
      <label>
        {label}
        {children}
      </label>
    ),
    Input: (props: any) => <input {...props} />,
    LoadingState: () => <p>loading</p>,
    Modal: ({ open, children, title }: any) =>
      open ? (
        <div role="dialog" aria-label={title}>
          {children}
        </div>
      ) : null,
    PageHeader: ({ title, description, action }: any) => (
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
        {action}
      </div>
    ),
    Select: ({ children, ...props }: any) => <select {...props}>{children}</select>,
    StatusBadge: ({ label, status }: any) => <span>{label ?? status}</span>,
    Table: P,
    Td: ({ children, ...rest }: any) => <td {...rest}>{children}</td>,
    Th: ({ children }: any) => <th>{children}</th>,
    Thead: P,
    Tr: ({ children, ...rest }: any) => <tr {...rest}>{children}</tr>,
  };
});

const {
  listTestEmailRecipients,
  createTestEmailRecipient,
  updateTestEmailRecipient,
} = vi.hoisted(() => ({
  listTestEmailRecipients: vi.fn(),
  createTestEmailRecipient: vi.fn(),
  updateTestEmailRecipient: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  listTestEmailRecipients,
  createTestEmailRecipient,
  updateTestEmailRecipient,
}));

import EmailSafetyPage from "../admin/email-safety/page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const RECIPIENT = {
  id: 1,
  email_address: "madushanka.weeriyasinghe@dijitalteam.com",
  display_label: "Madushanka - Internal Test",
  recipient_type: "INTERNAL_TESTER" as const,
  is_active: true,
  created_by: 7,
  updated_by: 7,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

describe("Email Safety admin page", () => {
  beforeEach(() => {
    isAdmin = true;
    listTestEmailRecipients.mockReset().mockResolvedValue({ items: [RECIPIENT] });
    createTestEmailRecipient.mockReset();
    updateTestEmailRecipient.mockReset();
  });

  it("loads and displays the approved recipient list with the safety banner", async () => {
    wrap(<EmailSafetyPage />);

    expect((await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Test Email Safety is active in this environment/)).toBeInTheDocument();
    expect(screen.getAllByText("Madushanka - Internal Test").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no approved recipients", async () => {
    listTestEmailRecipients.mockResolvedValue({ items: [] });
    wrap(<EmailSafetyPage />);

    expect(await screen.findByTestId("empty-state")).toHaveTextContent("No approved recipients yet");
  });

  it("shows an error state on API failure, with retry", async () => {
    listTestEmailRecipients.mockRejectedValue(new Error("boom"));
    wrap(<EmailSafetyPage />);

    expect(await screen.findByText("error")).toBeInTheDocument();
  });

  it("hides the page content for a non-admin user", async () => {
    isAdmin = false;
    wrap(<EmailSafetyPage />);

    expect(await screen.findByText("Admin access required")).toBeInTheDocument();
    expect(listTestEmailRecipients).not.toHaveBeenCalled();
  });

  it("adds a new recipient via the modal", async () => {
    const user = userEvent.setup();
    createTestEmailRecipient.mockResolvedValue({ ...RECIPIENT, id: 2 });
    wrap(<EmailSafetyPage />);
    await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com");

    await user.click(screen.getByRole("button", { name: /Add Recipient/i }));
    const dialog = await screen.findByRole("dialog");
    const emailInput = within(dialog).getByLabelText(/Email Address/i);
    await user.type(emailInput, "madusankaweeriyasinghe20@gmail.com");

    await user.click(within(dialog).getByRole("button", { name: /Add Recipient/i }));

    await waitFor(() =>
      expect(createTestEmailRecipient).toHaveBeenCalledWith(
        expect.objectContaining({ email_address: "madusankaweeriyasinghe20@gmail.com" })
      )
    );
  });

  it("rejects an invalid email address client-side without calling the API", async () => {
    const user = userEvent.setup();
    wrap(<EmailSafetyPage />);
    await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com");

    await user.click(screen.getByRole("button", { name: /Add Recipient/i }));
    const dialog = await screen.findByRole("dialog");
    const emailInput = within(dialog).getByLabelText(/Email Address/i);
    await user.type(emailInput, "not-an-email");

    const submitButton = within(dialog).getByRole("button", { name: /Add Recipient/i });
    expect(submitButton).toBeDisabled();
    expect(createTestEmailRecipient).not.toHaveBeenCalled();
  });

  it("surfaces a duplicate-recipient API error inside the modal", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@dijione/auth-client");
    createTestEmailRecipient.mockRejectedValue(new (ApiError as any)(409, "already an approved recipient"));
    wrap(<EmailSafetyPage />);
    await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com");

    await user.click(screen.getByRole("button", { name: /Add Recipient/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Email Address/i), "dup@dijitalteam.com");
    await user.click(within(dialog).getByRole("button", { name: /Add Recipient/i }));

    expect(await within(dialog).findByText("already an approved recipient")).toBeInTheDocument();
  });

  it("deactivates an active recipient via the runtime toggle, no redeploy required", async () => {
    const user = userEvent.setup();
    updateTestEmailRecipient.mockResolvedValue({ ...RECIPIENT, is_active: false });
    wrap(<EmailSafetyPage />);
    await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com");

    const deactivateButtons = screen.getAllByRole("button", { name: /Deactivate/i });
    await user.click(deactivateButtons[0]);

    await waitFor(() =>
      expect(updateTestEmailRecipient).toHaveBeenCalledWith(1, { is_active: false })
    );
  });

  it("edits a recipient's label and type without touching the address", async () => {
    const user = userEvent.setup();
    updateTestEmailRecipient.mockResolvedValue(RECIPIENT);
    wrap(<EmailSafetyPage />);
    await screen.findAllByText("madushanka.weeriyasinghe@dijitalteam.com");

    const editButtons = screen.getAllByRole("button", { name: /^Edit$/i });
    await user.click(editButtons[0]);
    const dialog = await screen.findByRole("dialog");
    const emailInput = within(dialog).getByLabelText(/Email Address/i) as HTMLInputElement;
    expect(emailInput).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: /Save Changes/i }));

    await waitFor(() =>
      expect(updateTestEmailRecipient).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ display_label: "Madushanka - Internal Test", recipient_type: "INTERNAL_TESTER" })
      )
    );
  });
});
