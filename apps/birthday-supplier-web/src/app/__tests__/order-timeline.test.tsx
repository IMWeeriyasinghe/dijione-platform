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

const { getPortalOrderTimeline, postPortalOrderMessage } = vi.hoisted(() => ({
  getPortalOrderTimeline: vi.fn(),
  postPortalOrderMessage: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ getPortalOrderTimeline, postPortalOrderMessage }));
vi.mock("@/lib/supplier-auth", () => ({ useSupplierAuth: () => ({ token: "t" }) }));

import type { PortalMe } from "@/lib/api";

const { usePortalMe } = vi.hoisted(() => ({
  usePortalMe: vi.fn<() => PortalMe | undefined>(() => undefined),
}));
vi.mock("@/lib/portal-me", () => ({ usePortalMe }));

import { OrderTimeline } from "../order-timeline";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("supplier OrderTimeline", () => {
  beforeEach(() => {
    getPortalOrderTimeline.mockResolvedValue({
      order_id: 5, order_reference: "BDAY-EMP1-2026-00001",
      entries: [
        { at: "2026-09-02T10:00:00Z", kind: "message", channel: "Portal", direction: "OUTBOUND",
          author_type: "USER", author_id: 1, title: "Internal · Portal message",
          body: "Deliver to reception.", meta: {} },
      ],
    });
    postPortalOrderMessage.mockResolvedValue({ order_id: 5, order_reference: "x", entries: [] });
  });

  it("shows internal→supplier messages and lets the supplier reply", async () => {
    wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByText("Internal · Portal message")).toBeInTheDocument();
    expect(screen.getByText("Deliver to reception.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Send a message to Dijital Team/), {
      target: { value: "will do" },
    });
    fireEvent.click(screen.getByText("Send"));
    await waitFor(() => expect(postPortalOrderMessage).toHaveBeenCalledWith("t", 5, "will do"));
  });

  it("hides the reply box in a read-only impersonation preview (§C)", async () => {
    usePortalMe.mockReturnValue({ supplier_name: "S", user_name: "U", read_only: true });
    wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByText("Internal · Portal message")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Send a message to Dijital Team/)).not.toBeInTheDocument();
    expect(screen.queryByText("Send")).not.toBeInTheDocument();
    usePortalMe.mockReturnValue(undefined);
  });

  it("hides the reply box on a COMPLETED order even when not read-only (§12)", async () => {
    wrap(<OrderTimeline orderId={5} orderStatus="COMPLETED" />);
    expect(await screen.findByText("Internal · Portal message")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Send a message to Dijital Team/)).not.toBeInTheDocument();
  });

  it("keeps the reply box open on an UNABLE_TO_FULFIL order (review correction #1)", async () => {
    wrap(<OrderTimeline orderId={5} orderStatus="UNABLE_TO_FULFIL" />);
    expect(await screen.findByText("Internal · Portal message")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Send a message to Dijital Team/)).toBeInTheDocument();
  });
});
