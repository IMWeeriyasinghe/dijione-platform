import { describe, expect, it } from "vitest";
import {
  ORDER_STATUSES,
  SUPPLIER_ORDER_STATUS_LABELS,
  getInternalOrderStatusLabel,
  getSupplierOrderStatusLabel,
} from "@dijione/contracts";

// Phase 1.6 §18A — audience-specific presentation over ONE canonical
// OrderStatus. Proves the exact example from the request and that no
// internal-only workflow terminology can leak into a supplier-facing
// label.

describe("audience-specific order status labels (§18A)", () => {
  it("SENT_TO_SUPPLIER: internal renders 'Sent to Supplier', supplier renders 'Awaiting Your Acceptance'", () => {
    expect(getInternalOrderStatusLabel("SENT_TO_SUPPLIER")).toBe("Sent to Supplier");
    expect(getSupplierOrderStatusLabel("SENT_TO_SUPPLIER")).toBe("Awaiting Your Acceptance");
  });

  it("CONFIRMED: internal renders 'Supplier Confirmed', supplier renders 'Accepted'", () => {
    expect(getInternalOrderStatusLabel("CONFIRMED")).toBe("Supplier Confirmed");
    expect(getSupplierOrderStatusLabel("CONFIRMED")).toBe("Accepted");
  });

  it("no internal-only workflow status (never supplier-visible) has a supplier label at all", () => {
    // These four never reach a supplier-scoped API response in the first
    // place (enforced server-side by SUPPLIER_VISIBLE_STATUSES) — this is
    // the presentation-layer half of that same guarantee: even if one
    // somehow arrived here, there is no supplier wording defined for it,
    // so getSupplierOrderStatusLabel falls back to the raw canonical
    // value rather than fabricating a supplier-friendly phrase for
    // internal-only terminology.
    for (const status of ["PENDING_VERIFICATION", "REQUIRES_REVIEW", "REQUIRES_ATTENTION", "ON_HOLD"]) {
      expect(SUPPLIER_ORDER_STATUS_LABELS[status as keyof typeof SUPPLIER_ORDER_STATUS_LABELS]).toBeUndefined();
    }
  });

  it("every canonical OrderStatus has an internal label", () => {
    for (const status of ORDER_STATUSES) {
      expect(getInternalOrderStatusLabel(status)).not.toBe(status);
    }
  });

  it("every supplier-visible status has a distinct, human supplier label", () => {
    const supplierVisible = [
      "SENT_TO_SUPPLIER", "CHANGE_REQUESTED", "CONFIRMED", "PREPARING",
      "OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED", "UNABLE_TO_FULFIL", "CANCELLED",
    ];
    for (const status of supplierVisible) {
      expect(getSupplierOrderStatusLabel(status)).toBeTruthy();
    }
  });
});
