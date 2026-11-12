import type { BirthdayOrderOut } from "@dijione/contracts";

/** Phase 1.6 §10 (R10) — one shared, pure policy function every button in
 * OrderDetail.tsx consumes, replacing five separately-named `canX` consts
 * plus three inline conditions. Mirrors the backend's own gates
 * (order_status_service.ALLOWED_TRANSITIONS / the route-level checks) so a
 * button can't drift out of sync with what the server actually allows —
 * the exact bug class this review found (Hold enabled on a terminal order,
 * §B row 3/4). This file changes no behaviour by itself; it's the
 * structural fix that stops that class of bug recurring silently. */

const TERMINAL_STATUSES = new Set(["CANCELLED", "COMPLETED", "DELIVERED"]);

export type OrderActionPolicy = {
  canVerify: boolean;
  canConfirmRelease: boolean;
  canSendToSupplier: boolean;
  canResend: boolean;
  canHold: boolean;
  canRelease: boolean;
  canCancel: boolean;
  canDelete: boolean;
  canReopen: boolean;
};

export function orderActionPolicy(order: BirthdayOrderOut): OrderActionPolicy {
  const status = order.status;
  return {
    canVerify: order.address_verification_status !== "VERIFIED" && !TERMINAL_STATUSES.has(status),
    canConfirmRelease: status === "REQUIRES_REVIEW",
    canSendToSupplier:
      ["PENDING_VERIFICATION", "REQUIRES_ATTENTION"].includes(status) &&
      order.supplier_id != null &&
      order.address_verification_status === "VERIFIED",
    canResend: ["REQUIRES_ATTENTION", "CHANGE_REQUESTED"].includes(status) && order.supplier_id != null,
    // Fix (R9): Hold used to only check `status !== "ON_HOLD"` — enabled
    // for COMPLETED/CANCELLED/DELIVERED, which the backend already 409s.
    canHold: !TERMINAL_STATUSES.has(status) && status !== "ON_HOLD",
    canRelease: status === "ON_HOLD",
    canCancel: !TERMINAL_STATUSES.has(status),
    // PENDING_VERIFICATION-only, never-actioned — the server is the real
    // boundary (409 otherwise); this mirrors it for the button state.
    canDelete: status === "PENDING_VERIFICATION",
    // §14 — the one deliberate exception to CANCELLED being terminal,
    // via the dedicated reopen_cancelled_order() endpoint only.
    canReopen: status === "CANCELLED",
  };
}
