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
    Textarea: (props: any) => <textarea {...props} />,
  };
});

const { getOrderTimeline, postOrderMessage } = vi.hoisted(() => ({
  getOrderTimeline: vi.fn(),
  postOrderMessage: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ getOrderTimeline, postOrderMessage }));

import { OrderTimeline } from "../OrderTimeline";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("OrderTimeline", () => {
  beforeEach(() => {
    getOrderTimeline.mockResolvedValue({
      order_id: 1, order_reference: "BDAY-EMP1-2026-00001",
      entries: [
        { at: "2026-09-01T10:00:00Z", kind: "email", channel: "Email", direction: "OUTBOUND",
          author_type: "SYSTEM", author_id: null, title: "System · Email", body: "released", meta: {} },
        { at: "2026-09-02T10:00:00Z", kind: "message", channel: "Portal", direction: "INBOUND",
          author_type: "SUPPLIER", author_id: 3, title: "Supplier · Portal message",
          body: "Can you clarify the building number?", meta: {} },
      ],
    });
    postOrderMessage.mockResolvedValue({ order_id: 1, order_reference: "x", entries: [] });
  });

  it("renders merged timeline entries from both channels/directions", async () => {
    wrap(<OrderTimeline orderId={1} />);
    expect(await screen.findByText("Supplier · Portal message")).toBeInTheDocument();
    expect(screen.getByText("Can you clarify the building number?")).toBeInTheDocument();
    expect(screen.getByText("System · Email")).toBeInTheDocument();
  });

  it("posts an internal message with the also-email option", async () => {
    wrap(<OrderTimeline orderId={1} />);
    await screen.findByText("System · Email");
    fireEvent.change(screen.getByPlaceholderText(/Post a message/), { target: { value: "on it" } });
    fireEvent.click(screen.getByLabelText(/email the supplier a copy/i));
    fireEvent.click(screen.getByText("Send"));
    await waitFor(() =>
      expect(postOrderMessage).toHaveBeenCalledWith(1, "on it", { also_email: true }),
    );
  });
});
