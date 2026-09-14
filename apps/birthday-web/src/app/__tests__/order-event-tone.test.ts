import { describe, expect, it } from "vitest";
import { getOrderEventTone, getOrderEventTypeLabel } from "@dijione/contracts";

// Phase 1.6 (post-hardening review round) — the Raw Event Log's semantic
// colour mapping, centralised so it's reused by the dot, left accent and
// (indirectly, via the existing StatusBadge tone) never colour-only.

describe("getOrderEventTone", () => {
  it("SUCCESS: confirmed, delivered, completed, email sent", () => {
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "CONFIRMED" })).toBe("success");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "DELIVERED" })).toBe("success");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "COMPLETED" })).toBe("success");
    expect(getOrderEventTone({ event_type: "EMAIL_SENT", to_status: null })).toBe("success");
  });

  it("WARNING/ACTION: pending verification, requires review/attention, on hold, reopened, preparing", () => {
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "PENDING_VERIFICATION" })).toBe("warning");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "REQUIRES_REVIEW" })).toBe("warning");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "REQUIRES_ATTENTION" })).toBe("warning");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "ON_HOLD" })).toBe("warning");
    expect(getOrderEventTone({ event_type: "REOPENED", to_status: null })).toBe("warning");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "PREPARING" })).toBe("warning");
  });

  it("IN PROGRESS: sent to supplier, out for delivery → brand orange, not warning or success", () => {
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "SENT_TO_SUPPLIER" })).toBe("progress");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "OUT_FOR_DELIVERY" })).toBe("progress");
  });

  it("ERROR/TERMINAL NEGATIVE: cancelled, unable to fulfil, email failures", () => {
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "CANCELLED" })).toBe("error");
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "UNABLE_TO_FULFIL" })).toBe("error");
    expect(getOrderEventTone({ event_type: "EMAIL_FAILED", to_status: null })).toBe("error");
    expect(getOrderEventTone({ event_type: "EMAIL_RETRY_EXHAUSTED", to_status: null })).toBe("error");
  });

  it("INFORMATIONAL: detected, assignment, system events default to info", () => {
    expect(getOrderEventTone({ event_type: "DETECTED", to_status: null })).toBe("info");
    expect(getOrderEventTone({ event_type: "SUPPLIER_ASSIGNED", to_status: null })).toBe("info");
    expect(getOrderEventTone({ event_type: "EMPLOYEE_NUMBER_ASSIGNED", to_status: null })).toBe("info");
    expect(getOrderEventTone({ event_type: "SOME_FUTURE_EVENT_TYPE", to_status: null })).toBe("info");
  });

  it("to_status takes precedence over event_type when both are present", () => {
    // A generic STATUS_CHANGE landing on CANCELLED must read as an error,
    // not fall through to some unrelated event_type-keyed tone.
    expect(getOrderEventTone({ event_type: "STATUS_CHANGE", to_status: "CANCELLED" })).toBe("error");
  });
});

describe("getOrderEventTypeLabel", () => {
  it("returns a human label for every known event_type, never the raw enum", () => {
    const knownTypes = [
      "STATUS_CHANGE", "DETECTED", "AUTO_RELEASED", "ADDRESS_VERIFICATION_CHANGE",
      "SUPPLIER_ASSIGNED", "EMPLOYEE_NUMBER_ASSIGNED", "DELIVERY_DATE_ADJUSTED",
      "EXCEPTION", "EXCEPTION_CLEARED", "EMAIL_SENT", "EMAIL_FAILED",
      "EMAIL_RETRY_EXHAUSTED", "ORDER_CHANGED_POST_RELEASE", "PORTAL_MESSAGE",
      "SUPPLIER_EMAIL_REPLY", "SUPPLIER_ISSUE", "REOPENED",
    ];
    for (const eventType of knownTypes) {
      const label = getOrderEventTypeLabel(eventType);
      expect(label).not.toBe(eventType);
      expect(label).not.toMatch(/_/);
    }
  });

  it("falls back to a readable title case for an unmapped event_type", () => {
    expect(getOrderEventTypeLabel("SOME_NEW_EVENT")).toBe("Some New Event");
  });
});
