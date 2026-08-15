"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  Send,
  Trash2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useBirthdayScope } from "@dijione/auth-client";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  FormField,
  LoadingState,
  Modal,
  Select,
  StatusBadge,
  Textarea,
} from "@dijione/design-system";
import {
  approveOrder,
  cancelOrder,
  deleteOrder,
  getOrder,
  holdOrder,
  rejectOrder,
  releaseOrder,
  resendOrderToSupplier,
  sendOrderToSupplier,
  submitForApproval,
  updateAddressVerification,
  updateDeliveryAddress,
} from "@/lib/api";
import type { DeliveryAddressUpdateInput } from "@dijione/contracts";

type ActionKind = "hold" | "release" | "cancel" | "reject" | null;

// P&C-manual only (plan requirement #7-9) — never set by automation, and
// setting one of these never triggers any outbound contact to the
// employee. P&C is expected to have already done their own outreach
// before choosing VERIFIED or NEEDS_UPDATE here.
const ADDRESS_VERIFICATION_OPTIONS = [
  "NOT_CHECKED",
  "VERIFICATION_REQUESTED",
  "VERIFIED",
  "NEEDS_UPDATE",
  "NOT_APPLICABLE",
];

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">{label}</span>
      <span className="text-sm text-dt-text-primary">{value}</span>
    </div>
  );
}

export function OrderDetail({ orderId }: { orderId: number }) {
  // Admin-only mutations (Hold / Release / Cancel) are hidden here for
  // non-admin personas as a UX convenience only. The real authorization
  // decision is made server-side by birthday-api's
  // `require_birthday_permission` dependency on every mutating route —
  // this client-side check is never the sole enforcement point (plan §11).
  const scope = useBirthdayScope();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [actionOpen, setActionOpen] = useState<ActionKind>(null);
  const [reasonText, setReasonText] = useState("");
  const [addressEditOpen, setAddressEditOpen] = useState(false);
  const [addressForm, setAddressForm] = useState<DeliveryAddressUpdateInput>({});

  const {
    data: order,
    isLoading,
    isError,
    refetch,
  } = useQuery({ queryKey: ["birthday-order", orderId], queryFn: () => getOrder(orderId) });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["birthday-order", orderId] });
    queryClient.invalidateQueries({ queryKey: ["birthday-orders"] });
    queryClient.invalidateQueries({ queryKey: ["birthday-dashboard"] });
  };

  const holdMutation = useMutation({
    mutationFn: (reason: string) => holdOrder(orderId, reason),
    onSuccess: () => {
      invalidate();
      setActionOpen(null);
      setReasonText("");
    },
  });

  const releaseMutation = useMutation({
    mutationFn: (note: string) => releaseOrder(orderId, note || undefined),
    onSuccess: () => {
      invalidate();
      setActionOpen(null);
      setReasonText("");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (reason: string) => cancelOrder(orderId, reason || undefined),
    onSuccess: () => {
      invalidate();
      setActionOpen(null);
      setReasonText("");
    },
  });

  const sendToSupplierMutation = useMutation({
    mutationFn: () => sendOrderToSupplier(orderId),
    onSuccess: () => invalidate(),
  });

  const resendMutation = useMutation({
    mutationFn: () => resendOrderToSupplier(orderId),
    onSuccess: () => invalidate(),
  });

  const addressVerificationMutation = useMutation({
    mutationFn: (newStatus: string) => updateAddressVerification(orderId, { status: newStatus }),
    onSuccess: () => invalidate(),
  });

  const addressEditMutation = useMutation({
    mutationFn: (payload: DeliveryAddressUpdateInput) => updateDeliveryAddress(orderId, payload),
    onSuccess: () => {
      invalidate();
      setAddressEditOpen(false);
    },
  });

  const submitForApprovalMutation = useMutation({
    mutationFn: () => submitForApproval(orderId),
    onSuccess: () => invalidate(),
  });

  const approveMutation = useMutation({
    mutationFn: () => approveOrder(orderId),
    onSuccess: () => invalidate(),
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => rejectOrder(orderId, { reason }),
    onSuccess: () => {
      invalidate();
      setActionOpen(null);
      setReasonText("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrder(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["birthday-orders"] });
      router.push("/orders");
    },
  });

  if (isLoading) return <LoadingState label="Loading order…" />;
  if (isError || !order) return <ErrorState onRetry={() => refetch()} />;

  const isMutating =
    holdMutation.isPending ||
    releaseMutation.isPending ||
    cancelMutation.isPending ||
    sendToSupplierMutation.isPending ||
    resendMutation.isPending ||
    submitForApprovalMutation.isPending ||
    approveMutation.isPending ||
    rejectMutation.isPending ||
    deleteMutation.isPending;

  // Approval workflow gate (Phase-Next §2): only an APPROVED order can be
  // sent — mirrors birthday-api's order_email_service._send check exactly,
  // this is a UX convenience only, never the enforcement point.
  const canSendToSupplier =
    order.status === "APPROVED" &&
    order.supplier_id != null &&
    order.address_verification_status === "VERIFIED";
  const canResend = ["REQUIRES_ATTENTION", "CHANGE_REQUESTED"].includes(order.status) && order.supplier_id != null;
  const canSubmitForApproval = order.status === "DRAFT";
  const canApproveOrReject = order.status === "READY_FOR_APPROVAL";
  // Hard delete is DRAFT-only and never-actioned (server is the real
  // boundary — see the 409 birthday-api returns otherwise).
  const canDelete = order.status === "DRAFT";

  function submitAction() {
    if (actionOpen === "hold") holdMutation.mutate(reasonText);
    if (actionOpen === "release") releaseMutation.mutate(reasonText);
    if (actionOpen === "cancel") cancelMutation.mutate(reasonText);
    if (actionOpen === "reject") rejectMutation.mutate(reasonText);
  }

  return (
    <div>
      <Link
        href="/orders"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
      >
        <ArrowLeft className="size-4" />
        Back to orders
      </Link>

      <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-dt-border bg-dt-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-dt-text-primary">{order.order_reference}</h1>
            <StatusBadge status={order.status} />
            {order.requires_admin_review && <StatusBadge status="PENDING" label="Needs review" />}
          </div>
          <p className="mt-1 text-sm text-dt-text-secondary">
            {order.employee_name} (
            {order.employee_number ?? `${order.employee_id} — internal id, no team member ID`}) ·{" "}
            {order.office_location}
          </p>
        </div>

        {scope?.isAdmin && (
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!canSubmitForApproval || isMutating}
              loading={submitForApprovalMutation.isPending}
              onClick={() => submitForApprovalMutation.mutate()}
            >
              Submit for Approval
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={!canApproveOrReject || isMutating}
              loading={approveMutation.isPending}
              onClick={() => approveMutation.mutate()}
            >
              <CheckCircle2 className="size-4" />
              Approve
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={!canApproveOrReject || isMutating}
              onClick={() => setActionOpen("reject")}
            >
              <XCircle className="size-4" />
              Reject
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!canSendToSupplier || isMutating}
              loading={sendToSupplierMutation.isPending}
              onClick={() => sendToSupplierMutation.mutate()}
            >
              <Send className="size-4" />
              Send to Supplier
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={!canResend || isMutating}
              loading={resendMutation.isPending}
              onClick={() => resendMutation.mutate()}
            >
              <RefreshCcw className="size-4" />
              Resend
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={order.status === "ON_HOLD" || isMutating}
              onClick={() => setActionOpen("hold")}
            >
              <PauseCircle className="size-4" />
              Hold
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={order.status !== "ON_HOLD" || isMutating}
              onClick={() => setActionOpen("release")}
            >
              <PlayCircle className="size-4" />
              Release
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={["CANCELLED", "COMPLETED"].includes(order.status) || isMutating}
              onClick={() => setActionOpen("cancel")}
            >
              <XCircle className="size-4" />
              Cancel
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={!canDelete || isMutating}
              loading={deleteMutation.isPending}
              title={!canDelete ? "Only never-actioned DRAFT orders can be deleted — use Cancel instead" : undefined}
              onClick={() => {
                if (window.confirm("Permanently delete this draft order? This cannot be undone.")) {
                  deleteMutation.mutate();
                }
              }}
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Order Details</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <DetailRow label="Team Member Email" value={order.employee_email} />
              <DetailRow label="Birthday" value={`${order.birthday_date} (${order.birthday_year})`} />
              <DetailRow label="Detected At" value={order.detected_at ?? "—"} />
              <DetailRow label="Lead Time" value={`${order.lead_time_days} days`} />
              <DetailRow label="Lead Time Class" value={<StatusBadge status={order.lead_time_class} />} />
              <DetailRow label="Quantity" value={order.quantity} />
              <DetailRow label="Delivery Date" value={order.delivery_date ?? "—"} />
              <DetailRow label="Supplier" value={order.supplier_id ?? "Unassigned"} />
              <DetailRow label="Manual Override" value={order.is_manual_override ? "Yes" : "No"} />
              <DetailRow label="Overdue" value={order.is_overdue ? "Yes" : "No"} />
              <DetailRow label="Delivery Issue" value={order.has_delivery_issue ? "Yes" : "No"} />
              <DetailRow label="Retry Count" value={order.retry_count} />
              {order.hold_reason && <DetailRow label="Hold Reason" value={order.hold_reason} />}
              {order.last_failure_reason && (
                <DetailRow label="Last Failure" value={order.last_failure_reason} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Address Verification</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-dt-text-secondary">
                P&C-manual only — set this after confirming the delivery address directly with the
                team member. Nothing here contacts the team member automatically, and the order
                cannot be sent to the supplier until this is <strong>Verified</strong>.
              </p>

              <div className="mb-3 rounded-xl border border-dt-border p-3">
                {order.delivery_address_line1 ||
                order.delivery_city ||
                order.delivery_state_province ||
                order.delivery_country ? (
                  <>
                    <p className="text-sm text-dt-text-primary">
                      {[order.delivery_address_line1, order.delivery_address_line2].filter(Boolean).join(", ") ||
                        "—"}
                    </p>
                    <p className="text-sm text-dt-text-primary">
                      {[order.delivery_city, order.delivery_state_province, order.delivery_postal_code]
                        .filter(Boolean)
                        .join(", ")}
                    </p>
                    <p className="text-sm text-dt-text-primary">{order.delivery_country}</p>
                    <p className="mt-1 text-xs text-dt-text-secondary">
                      Source: {order.delivery_address_source === "MANUAL_CORRECTION" ? "Manually corrected" : "BambooHR"}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-dt-text-secondary">No address on file.</p>
                )}
                {scope?.isAdmin && (
                  <Button
                    size="sm"
                    variant="secondary"
                    className="mt-2"
                    onClick={() => {
                      setAddressForm({
                        delivery_address_line1: order.delivery_address_line1 ?? "",
                        delivery_address_line2: order.delivery_address_line2 ?? "",
                        delivery_city: order.delivery_city ?? "",
                        delivery_state_province: order.delivery_state_province ?? "",
                        delivery_postal_code: order.delivery_postal_code ?? "",
                        delivery_country: order.delivery_country ?? "",
                      });
                      setAddressEditOpen(true);
                    }}
                  >
                    Edit address
                  </Button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <StatusBadge status={order.address_verification_status} />
                {scope?.isAdmin && (
                  <Select
                    value={order.address_verification_status}
                    disabled={addressVerificationMutation.isPending}
                    onChange={(e) => addressVerificationMutation.mutate(e.target.value)}
                    className="w-auto"
                  >
                    {ADDRESS_VERIFICATION_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {s.replace(/_/g, " ")}
                      </option>
                    ))}
                  </Select>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Special Requirements</CardTitle>
            </CardHeader>
            <CardContent>
              {order.special_requirements.length === 0 ? (
                <p className="text-sm text-dt-text-secondary">No special requirements recorded.</p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {order.special_requirements.map((req) => (
                    <li key={req.id} className="rounded-xl border border-dt-border p-3">
                      <span
                        className={
                          req.kind === "SUPPLIER_INSTRUCTION"
                            ? "text-xs font-semibold uppercase tracking-wide text-dt-burnt-orange"
                            : "text-xs font-semibold uppercase tracking-wide text-dt-info"
                        }
                      >
                        {req.kind === "SUPPLIER_INSTRUCTION" ? "Supplier instruction" : "Internal note"}
                      </span>
                      <p className="mt-1 text-sm text-dt-text-primary">{req.text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Supplier Communications</CardTitle>
            </CardHeader>
            <CardContent>
              {/* birthday-api's BirthdayOrderRead does not yet include a
                  `communications` field, so there is nothing to list here
                  today. Send/Resend actions above still work — this card
                  will start rendering entries automatically once the
                  backend response includes them, no frontend change
                  required beyond adding the field to BirthdayOrderOut. */}
              <p className="text-sm text-dt-text-secondary">
                Supplier communication history is not yet exposed by the order API. Use Order History
                below to see send/resend events in the meantime.
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Order History</CardTitle>
          </CardHeader>
          <CardContent>
            {order.events.length === 0 ? (
              <p className="text-sm text-dt-text-secondary">No events recorded.</p>
            ) : (
              <ol className="flex flex-col gap-4">
                {order.events.map((event) => (
                  <li key={event.id} className="border-l-2 border-dt-border pl-3">
                    <p className="text-sm font-medium text-dt-text-primary">
                      {event.event_type.replace(/_/g, " ")}
                    </p>
                    {event.from_status && event.to_status && (
                      <p className="text-xs text-dt-text-secondary">
                        {event.from_status} → {event.to_status}
                      </p>
                    )}
                    {event.detail && <p className="mt-0.5 text-xs text-dt-text-secondary">{event.detail}</p>}
                    <p className="mt-0.5 text-xs text-dt-text-secondary">
                      {new Date(event.created_at).toLocaleString()} · {event.actor_type}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>

      <Modal
        open={actionOpen !== null}
        onClose={() => {
          setActionOpen(null);
          setReasonText("");
        }}
        title={
          actionOpen === "hold"
            ? "Put order on hold"
            : actionOpen === "release"
              ? "Release order from hold"
              : actionOpen === "reject"
                ? "Reject order"
                : "Cancel order"
        }
      >
        <div className="flex flex-col gap-4">
          <FormField
            label={actionOpen === "release" ? "Note (optional)" : "Reason"}
            htmlFor="action-reason"
            required={actionOpen !== "release"}
          >
            <Textarea
              id="action-reason"
              value={reasonText}
              onChange={(e) => setReasonText(e.target.value)}
              placeholder={actionOpen === "hold" ? "Why is this order on hold?" : "Optional detail"}
            />
          </FormField>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setActionOpen(null)}>
              Cancel
            </Button>
            <Button
              variant={actionOpen === "cancel" || actionOpen === "reject" ? "danger" : "primary"}
              size="sm"
              loading={isMutating}
              disabled={(actionOpen === "hold" || actionOpen === "reject") && reasonText.trim() === ""}
              onClick={submitAction}
            >
              Confirm
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={addressEditOpen} onClose={() => setAddressEditOpen(false)} title="Edit delivery address">
        <div className="flex flex-col gap-4">
          <FormField label="Address Line 1" htmlFor="addr-line1">
            <input
              id="addr-line1"
              className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
              value={addressForm.delivery_address_line1 ?? ""}
              onChange={(e) => setAddressForm((f) => ({ ...f, delivery_address_line1: e.target.value }))}
            />
          </FormField>
          <FormField label="Address Line 2" htmlFor="addr-line2">
            <input
              id="addr-line2"
              className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
              value={addressForm.delivery_address_line2 ?? ""}
              onChange={(e) => setAddressForm((f) => ({ ...f, delivery_address_line2: e.target.value }))}
            />
          </FormField>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="City" htmlFor="addr-city">
              <input
                id="addr-city"
                className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
                value={addressForm.delivery_city ?? ""}
                onChange={(e) => setAddressForm((f) => ({ ...f, delivery_city: e.target.value }))}
              />
            </FormField>
            <FormField label="Province / State" htmlFor="addr-state">
              <input
                id="addr-state"
                className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
                value={addressForm.delivery_state_province ?? ""}
                onChange={(e) => setAddressForm((f) => ({ ...f, delivery_state_province: e.target.value }))}
              />
            </FormField>
            <FormField label="Postal Code" htmlFor="addr-postal">
              <input
                id="addr-postal"
                className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
                value={addressForm.delivery_postal_code ?? ""}
                onChange={(e) => setAddressForm((f) => ({ ...f, delivery_postal_code: e.target.value }))}
              />
            </FormField>
            <FormField label="Country" htmlFor="addr-country">
              <input
                id="addr-country"
                className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
                value={addressForm.delivery_country ?? ""}
                onChange={(e) => setAddressForm((f) => ({ ...f, delivery_country: e.target.value }))}
              />
            </FormField>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setAddressEditOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={addressEditMutation.isPending}
              onClick={() => addressEditMutation.mutate(addressForm)}
            >
              Save address
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
