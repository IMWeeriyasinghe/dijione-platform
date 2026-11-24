import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MockButtonProps, MockTextareaProps } from "@/test-support/mock-props";

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    Button: ({ children, onClick, disabled }: MockButtonProps) => (
      <button onClick={onClick} disabled={disabled}>{children}</button>
    ),
    Card: P, CardContent: P, CardHeader: P, CardTitle: P,
    Textarea: (props: MockTextareaProps) => <textarea {...props} />,
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

describe("supplier OrderTimeline — email activity rendering", () => {
  const HTML = `<!doctype html><html><head></head><body style="margin:0"><table><tr><td>
    <h1>New Birthday Cake Order</h1><script>alert(1)</script><p onclick="x()">Benedict Hashanth</p>
    </td></tr></table></body></html>`;
  const SUBJECT = "[BDAY-EMP252-2026-00621] New Birthday Cake Order — Benedict Hashanth";

  function timeline(entries: unknown[]) {
    getPortalOrderTimeline.mockResolvedValue({ order_id: 5, order_reference: "BDAY-EMP252-2026-00621", entries });
  }

  it("renders an HTML email inside a sandboxed preview, never as raw markup", async () => {
    timeline([
      { at: "2026-11-23T05:12:00Z", kind: "email", channel: "Email", direction: "OUTBOUND", author_type: "SYSTEM",
        author_id: null, title: `System · Email — ${SUBJECT}`, body: HTML, body_format: "html", subject: SUBJECT,
        meta: {} },
    ]);
    const { container } = wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByText("System · Email")).toBeInTheDocument();
    expect(screen.getByTestId("email-subject")).toHaveTextContent(SUBJECT);
    const frame = screen.getByTestId("email-preview") as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toBe("");
    const src = frame.getAttribute("srcdoc") ?? "";
    expect(src).toContain("<h1>New Birthday Cake Order</h1>");
    expect(src).not.toMatch(/<script|onclick|alert\(/);
    // No literal markup anywhere in the page text.
    expect(container.textContent).not.toMatch(/<!doctype|<html|<body|<table/i);
  });

  it("detects HTML from older responses without body_format", async () => {
    timeline([
      { at: "2026-09-28T10:00:00Z", kind: "email", channel: "Email", direction: "OUTBOUND", author_type: "SYSTEM",
        author_id: null, title: "System · Email — Old order", body: HTML, meta: {} },
    ]);
    const { container } = wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByTestId("email-preview")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/<!doctype|<html/i);
  });

  it("shows a plain-text email as text and expands a long email on request", async () => {
    timeline([
      { at: "2026-11-23T05:00:00Z", kind: "email", channel: "Email", direction: "INBOUND", author_type: "SUPPLIER",
        author_id: 3, title: "Supplier · Email — Re: order", body: "Thanks, confirmed.", body_format: "text",
        subject: "Re: order", meta: {} },
      { at: "2026-11-23T06:00:00Z", kind: "email", channel: "Email", direction: "OUTBOUND", author_type: "SYSTEM",
        author_id: null, title: "System · Email — Long", body: `<p>${"long line ".repeat(2000)}</p>`,
        body_format: "html", subject: "Long", meta: {} },
    ]);
    wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByText("Thanks, confirmed.")).toBeInTheDocument();
    const frame = screen.getByTestId("email-preview") as HTMLIFrameElement;
    expect(frame.style.height).toBe("320px");
    fireEvent.click(screen.getByText("Show full email"));
    expect(frame.style.height).toBe("900px");
  });

  it("leaves supplier messages and events unchanged and keeps the order", async () => {
    timeline([
      { at: "2026-11-23T05:00:00Z", kind: "email", channel: "Email", direction: "OUTBOUND", author_type: "SYSTEM",
        author_id: null, title: `System · Email — ${SUBJECT}`, body: HTML, body_format: "html", subject: SUBJECT, meta: {} },
      { at: "2026-11-23T06:00:00Z", kind: "message", channel: "Portal", direction: "INBOUND", author_type: "SUPPLIER",
        author_id: 3, title: "Supplier · Portal message", body: "<b>not html</b> just text", meta: {} },
      { at: "2026-11-23T07:00:00Z", kind: "event", channel: "System", direction: null, author_type: "SYSTEM",
        author_id: null, title: "Status changed", body: "CONFIRMED", meta: {} },
    ]);
    wrap(<OrderTimeline orderId={5} />);
    expect(await screen.findByText("Supplier · Portal message")).toBeInTheDocument();
    expect(screen.getByText("<b>not html</b> just text")).toBeInTheDocument(); // escaped as text, as before
    const titles = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(titles[0]).toContain("System · Email");
    expect(titles[1]).toContain("Supplier · Portal message");
    expect(titles[2]).toContain("Status changed");
  });
});
