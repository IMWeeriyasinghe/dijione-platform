import { describe, expect, it } from "vitest";
import { supplierActionPolicy } from "@/lib/supplier-action-policy";

describe("supplierActionPolicy (Phase 1.6 §12/§19, review correction #1)", () => {
  it("hides Report a Problem on every fulfilment-terminal status", () => {
    for (const status of ["DELIVERED", "COMPLETED", "CANCELLED", "UNABLE_TO_FULFIL"]) {
      expect(supplierActionPolicy(status, false).canReportProblem).toBe(false);
    }
  });

  it("blocks messaging only on COMPLETED/CANCELLED — NOT on UNABLE_TO_FULFIL or DELIVERED", () => {
    expect(supplierActionPolicy("COMPLETED", false).canMessage).toBe(false);
    expect(supplierActionPolicy("CANCELLED", false).canMessage).toBe(false);
    // The review's explicit correction: operations/supplier still need to
    // discuss reassignment/recovery here — do not close communication.
    expect(supplierActionPolicy("UNABLE_TO_FULFIL", false).canMessage).toBe(true);
    expect(supplierActionPolicy("DELIVERED", false).canMessage).toBe(true);
    expect(supplierActionPolicy("SENT_TO_SUPPLIER", false).canMessage).toBe(true);
  });

  it("read-only impersonation disables everything regardless of status", () => {
    const p = supplierActionPolicy("SENT_TO_SUPPLIER", true);
    expect(p.canAccept).toBe(false);
    expect(p.canReportProblem).toBe(false);
    expect(p.canMessage).toBe(false);
    expect(p.nextStatusOptions).toEqual([]);
  });

  it("Accept is only offered from SENT_TO_SUPPLIER", () => {
    expect(supplierActionPolicy("SENT_TO_SUPPLIER", false).canAccept).toBe(true);
    expect(supplierActionPolicy("CONFIRMED", false).canAccept).toBe(false);
  });

  it("nextStatusOptions never includes CONFIRMED (reached via Accept instead)", () => {
    expect(supplierActionPolicy("SENT_TO_SUPPLIER", false).nextStatusOptions).not.toContain("CONFIRMED");
  });
});
