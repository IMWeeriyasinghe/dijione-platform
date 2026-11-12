import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    Button: ({ children, onClick, disabled }: any) => (
      <button onClick={onClick} disabled={disabled}>{children}</button>
    ),
    Card: P, CardContent: P, CardHeader: P, CardTitle: P,
    EmptyState: ({ title }: any) => <p>{title}</p>,
    ErrorState: () => <p>error</p>,
    LoadingState: () => <p>loading</p>,
    PageHeader: ({ title }: any) => <h1>{title}</h1>,
    FormField: ({ children, label }: any) => <label>{label}{children}</label>,
    Input: (props: any) => <input {...props} />,
  };
});

const { listUnmatchedEmails, linkUnmatchedEmail, dismissUnmatchedEmail } = vi.hoisted(() => ({
  listUnmatchedEmails: vi.fn(),
  linkUnmatchedEmail: vi.fn(),
  dismissUnmatchedEmail: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ listUnmatchedEmails, linkUnmatchedEmail, dismissUnmatchedEmail }));

import UnmatchedEmailsPage from "../inbound-emails/page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const ROW = {
  id: 7, from_address: "baker@x.example.com", subject: "Re: order",
  body_preview: "van broke down", received_at: null, attachment_count: 0,
  status: "UNMATCHED", reason: "no order reference", linked_order_id: null,
  created_at: "2026-09-09T00:00:00Z",
};

describe("UnmatchedEmailsPage", () => {
  beforeEach(() => {
    listUnmatchedEmails.mockResolvedValue([ROW]);
    linkUnmatchedEmail.mockResolvedValue({ ...ROW, status: "LINKED" });
    dismissUnmatchedEmail.mockResolvedValue({ ...ROW, status: "DISMISSED" });
  });

  it("links by a numeric order id", async () => {
    wrap(<UnmatchedEmailsPage />);
    expect(await screen.findByText("Re: order")).toBeInTheDocument();
    expect(screen.getByText("van broke down")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Link to an order"));
    fireEvent.change(screen.getByPlaceholderText("e.g. BDAY-EMP239-2026-00001"), {
      target: { value: "42" },
    });
    fireEvent.click(screen.getByText("Link"));

    await waitFor(() =>
      expect(linkUnmatchedEmail).toHaveBeenCalledWith(7, { order_id: 42, raise_issue: false }),
    );
  });

  it("links by an order reference (§H4 — operators know the reference, not the id)", async () => {
    wrap(<UnmatchedEmailsPage />);
    fireEvent.click(await screen.findByText("Link to an order"));
    fireEvent.change(screen.getByPlaceholderText("e.g. BDAY-EMP239-2026-00001"), {
      target: { value: "BDAY-EMP239-2026-00001" },
    });
    fireEvent.click(screen.getByText("Link"));

    await waitFor(() =>
      expect(linkUnmatchedEmail).toHaveBeenCalledWith(7, {
        order_reference: "BDAY-EMP239-2026-00001",
        raise_issue: false,
      }),
    );
  });

  it("dismisses a quarantined email", async () => {
    wrap(<UnmatchedEmailsPage />);
    fireEvent.click(await screen.findByText("Dismiss"));
    await waitFor(() => expect(dismissUnmatchedEmail).toHaveBeenCalledWith(7), { timeout: 3000 });
  });
});
