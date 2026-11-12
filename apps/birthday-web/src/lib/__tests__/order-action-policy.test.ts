import { describe, expect, it } from "vitest";
import { orderActionPolicy } from "@/lib/order-action-policy";
import type { BirthdayOrderOut } from "@dijione/contracts";

function order(overrides: Partial<Omit<BirthdayOrderOut, "status">> & { status: string }): BirthdayOrderOut {
  return {
    id: 1, order_reference: "BDAY-EMP1-2026-00001", employee_id: "1", employee_number: "1",
    employee_name: "Test", employee_email: "t@example.com", birthday_date: "2026-10-01",
    birthday_year: 2026, office_location: "Colombo", detected_at: null, lead_time_days: 20,
    lead_time_class: "NORMAL", quantity: 1, hold_reason: null,
    address_verification_status: "NOT_CHECKED", delivery_address_line1: null,
    delivery_address_line2: null, delivery_city: null, delivery_state_province: null,
    delivery_postal_code: null, delivery_country: null, delivery_address_source: null,
    supplier_id: null, supplier_name: null, delivery_date: null, catalogue_item_id: null,
    is_manual_override: false, requires_admin_review: false, exception_reason: null,
    verify_by: null, retry_count: 0, last_failure_reason: null, released_at: null,
    released_by: null, review_confirmed_at: null, review_confirmed_by: null, accepted_at: null,
    preparing_at: null, out_for_delivery_at: null, delivered_at: null, completed_at: null,
    created_by: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    events: [], special_requirements: [], issues: [],
    ...overrides,
  } as BirthdayOrderOut;
}

describe("orderActionPolicy (Phase 1.6 §10/R9/R10)", () => {
  it.each(["COMPLETED", "CANCELLED", "DELIVERED"])(
    "disables Hold on a terminal order (%s) — the exact bug this review found",
    (status) => {
      expect(orderActionPolicy(order({ status })).canHold).toBe(false);
    },
  );

  it("enables Hold on a normal, non-held, non-terminal order", () => {
    expect(orderActionPolicy(order({ status: "PENDING_VERIFICATION" })).canHold).toBe(true);
  });

  it("disables Hold when already ON_HOLD", () => {
    expect(orderActionPolicy(order({ status: "ON_HOLD" })).canHold).toBe(false);
  });

  it("only CANCELLED is reopenable", () => {
    expect(orderActionPolicy(order({ status: "CANCELLED" })).canReopen).toBe(true);
    expect(orderActionPolicy(order({ status: "COMPLETED" })).canReopen).toBe(false);
    expect(orderActionPolicy(order({ status: "DELIVERED" })).canReopen).toBe(false);
    expect(orderActionPolicy(order({ status: "PENDING_VERIFICATION" })).canReopen).toBe(false);
  });

  it("disables Cancel on every terminal status", () => {
    for (const status of ["COMPLETED", "CANCELLED", "DELIVERED"]) {
      expect(orderActionPolicy(order({ status })).canCancel).toBe(false);
    }
  });

  it("Delete is PENDING_VERIFICATION-only", () => {
    expect(orderActionPolicy(order({ status: "PENDING_VERIFICATION" })).canDelete).toBe(true);
    expect(orderActionPolicy(order({ status: "REQUIRES_ATTENTION" })).canDelete).toBe(false);
  });
});
