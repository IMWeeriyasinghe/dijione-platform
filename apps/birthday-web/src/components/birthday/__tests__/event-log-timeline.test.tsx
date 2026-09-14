import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { OrderEventOut } from "@dijione/contracts";
import { EventLogTimeline } from "../EventLogTimeline";

// Phase 1.6 (post-hardening review round) — Raw Event Log visual uplift.
// Keeps every field the flat list already showed (event, transition,
// detail, timestamp, actor); only the rendering changes to a vertical
// timeline. These tests pin: no information is dropped, raw enum values
// never reach the screen, actor_display_name is preferred over actor_type,
// and every semantic tone bucket resolves as specified.

vi.mock("@dijione/design-system", () => ({
  StatusBadge: ({ status, label }: { status: string; label?: string }) => (
    <span data-testid={`status-badge-${status}`}>{label ?? status}</span>
  ),
}));

function event(overrides: Partial<OrderEventOut>): OrderEventOut {
  return {
    id: 1,
    event_type: "STATUS_CHANGE",
    from_status: null,
    to_status: null,
    actor_id: null,
    actor_type: "USER",
    actor_display_name: null,
    detail: null,
    created_at: "2026-09-14T06:43:20Z",
    ...overrides,
  };
}

function wrap(ui: ReactNode) {
  return render(ui);
}

describe("EventLogTimeline (Raw Event Log visual uplift)", () => {
  it("renders every event passed to it — no information is dropped", () => {
    wrap(
      <EventLogTimeline
        events={[event({ id: 1, event_type: "DETECTED" }), event({ id: 2, event_type: "AUTO_RELEASED" }), event({ id: 3, event_type: "REOPENED" })]}
      />
    );
    expect(screen.getByText("Detected")).toBeInTheDocument();
    expect(screen.getByText("Auto Released")).toBeInTheDocument();
    expect(screen.getByText("Order Reopened")).toBeInTheDocument();
  });

  it("shows 'No events recorded.' for an empty order, not an empty list", () => {
    wrap(<EventLogTimeline events={[]} />);
    expect(screen.getByText("No events recorded.")).toBeInTheDocument();
  });

  it("renders a human label for the event type, never the raw enum string", () => {
    wrap(<EventLogTimeline events={[event({ event_type: "EMAIL_RETRY_EXHAUSTED" })]} />);
    expect(screen.getByText("Email Retries Exhausted")).toBeInTheDocument();
    expect(screen.queryByText("EMAIL_RETRY_EXHAUSTED")).not.toBeInTheDocument();
  });

  it("renders human-readable status transitions, not raw enum values (§3)", () => {
    wrap(
      <EventLogTimeline
        events={[event({ event_type: "STATUS_CHANGE", from_status: "PENDING_VERIFICATION", to_status: "SENT_TO_SUPPLIER" })]}
      />
    );
    expect(screen.getByText("Pending Verification → Sent to Supplier")).toBeInTheDocument();
    expect(screen.queryByText("PENDING_VERIFICATION → SENT_TO_SUPPLIER")).not.toBeInTheDocument();
  });

  it("shows the actual actor_display_name when available", () => {
    wrap(
      <EventLogTimeline
        events={[event({ actor_display_name: "Kumar Sangakkara", actor_type: "USER" })]}
      />
    );
    expect(screen.getByText(/Kumar Sangakkara/)).toBeInTheDocument();
  });

  it("falls back to actor_type only when actor_display_name is genuinely unavailable", () => {
    wrap(<EventLogTimeline events={[event({ actor_display_name: null, actor_type: "SYSTEM" })]} />);
    expect(screen.getByText(/SYSTEM/)).toBeInTheDocument();
  });

  it("keeps the event detail text", () => {
    wrap(<EventLogTimeline events={[event({ detail: "Order automatically released after address verification" })]} />);
    expect(screen.getByText("Order automatically released after address verification")).toBeInTheDocument();
  });

  it("shows a status badge with the human label when the event carries a to_status", () => {
    wrap(<EventLogTimeline events={[event({ to_status: "SENT_TO_SUPPLIER" })]} />);
    expect(screen.getByTestId("status-badge-SENT_TO_SUPPLIER")).toHaveTextContent("Sent to Supplier");
  });

  it("does not render a status badge when the event has no to_status", () => {
    wrap(<EventLogTimeline events={[event({ to_status: null })]} />);
    expect(screen.queryByTestId(/status-badge-/)).not.toBeInTheDocument();
  });

  it("preserves chronological order exactly as given", () => {
    wrap(
      <EventLogTimeline
        events={[
          event({ id: 1, event_type: "DETECTED" }),
          event({ id: 2, event_type: "SUPPLIER_ASSIGNED" }),
          event({ id: 3, event_type: "AUTO_RELEASED" }),
        ]}
      />
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Detected");
    expect(items[1]).toHaveTextContent("Supplier Assigned");
    expect(items[2]).toHaveTextContent("Auto Released");
  });
});
