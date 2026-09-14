import { SUPPLIER_DRIVABLE_TARGETS } from "@dijione/contracts";

/** Phase 1.6 §12 (R19) — one shared policy function, mirroring the
 * internal app's orderActionPolicy, so "what can a supplier do to this
 * order" lives in one place instead of a `readOnly ? … : …` scattered per
 * component. Two DIFFERENT status sets on purpose (review correction #1):
 * fulfilment-terminal (used for status progression) vs. the narrower
 * communication-closed set (only COMPLETED/CANCELLED — UNABLE_TO_FULFIL
 * deliberately stays open for messages). */

const FULFILMENT_TERMINAL_STATUSES = new Set(["DELIVERED", "COMPLETED", "CANCELLED", "UNABLE_TO_FULFIL"]);
const COMMUNICATION_CLOSED_STATUSES = new Set(["COMPLETED", "CANCELLED"]);

export type SupplierActionPolicy = {
  canAccept: boolean;
  nextStatusOptions: string[];
  canReportProblem: boolean;
  canMessage: boolean;
  isTerminal: boolean;
};

export function supplierActionPolicy(status: string, readOnly: boolean): SupplierActionPolicy {
  const isTerminal = FULFILMENT_TERMINAL_STATUSES.has(status);
  return {
    canAccept: !readOnly && status === "SENT_TO_SUPPLIER",
    // CONFIRMED is reached via Accept, not a status pill — avoid showing
    // "Confirm / Accept" twice for the same transition.
    nextStatusOptions: readOnly ? [] : (SUPPLIER_DRIVABLE_TARGETS[status] ?? []).filter((s) => s !== "CONFIRMED"),
    canReportProblem: !readOnly && !isTerminal,
    canMessage: !readOnly && !COMMUNICATION_CLOSED_STATUSES.has(status),
    isTerminal,
  };
}
