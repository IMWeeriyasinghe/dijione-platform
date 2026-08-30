"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
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
  cancelOrder,
  confirmRelease,
  deleteOrder,
  getOrder,
  holdOrder,
  listSupplierCatalogue,
  listSuppliers,
  releaseOrder,
  resendOrderToSupplier,
  sendOrderToSupplier,
  updateAddressVerification,
  updateDeliveryAddress,
  updateOrder,
  verifyAddress,
} from "@/lib/api";
import type { BirthdayOrderOut, DeliveryAddressUpdateInput, SupplierOut } from "@dijione/contracts";

type ActionKind = "hold" | "release" | "cancel" | null;

type FulfilmentEdit = { supplier_id?: string; delivery_date?: string; catalogue_item_id?: string };

/** Resolves the *effective* fulfilment values shown in the assignment panel:
 * an unsaved operator edit wins; otherwise the value already on the order;
 * otherwise a safe system default — the sole ACTIVE supplier (§5/§6) for
 * supplier, and the birthday occurrence (§8) for delivery date. Product
 * type is always "Cake" and is not part of this (§7). */
function effectiveFulfilment(order: BirthdayOrderOut, activeSuppliers: SupplierOut[], edit: FulfilmentEdit) {
  const soleSupplierId = activeSuppliers.length === 1 ? String(activeSuppliers[0].id) : "";
  return {
    supplierId: edit.supplier_id ?? (order.supplier_id != null ? String(order.supplier_id) : soleSupplierId),
    deliveryDate: edit.delivery_date ?? order.delivery_date ?? order.birthday_date ?? "",
    catalogueId:
      edit.catalogue_item_id ?? (order.catalogue_item_id != null ? String(order.catalogue_item_id) : ""),
  };
}

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
  // Fulfilment-assignment edits. Each field is `undefined` until the
  // operator touches it, then a string (including "" to clear) — so a
  // touched-then-emptied field stays empty rather than snapping back to the
  // order's value. Avoids seeding state from an effect.
  const [fulfilmentEdit, setFulfilmentEdit] = useState<FulfilmentEdit>({});

  const {
    data: order,
    isLoading,
    isError,
    refetch,
  } = useQuery({ queryKey: ["birthday-order", orderId], queryFn: () => getOrder(orderId) });

  const suppliersQuery = useQuery({
    queryKey: ["birthday-suppliers-picker"],
    queryFn: () => listSuppliers({ page_size: 200 }),
  });

  const suppliers = suppliersQuery.data?.items ?? [];
  const activeSuppliers = suppliers.filter((s) => s.status === "ACTIVE");
  const eff = order
    ? effectiveFulfilment(order, activeSuppliers, fulfilmentEdit)
    : { supplierId: "", deliveryDate: "", catalogueId: "" };

  const catalogueQuery = useQuery({
    queryKey: ["birthday-order-catalogue", eff.supplierId],
    queryFn: () => listSupplierCatalogue(Number(eff.supplierId)),
    enabled: eff.supplierId !== "",
  });

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

  // "Verification is the approval" (plan §K) — this one call is the
  // entire routine happy path. A standard order auto-releases straight
  // to SENT_TO_SUPPLIER; a flagged order lands in REQUIRES_REVIEW for
  // the one-click confirmReleaseMutation below.
  const verifyMutation = useMutation({
    mutationFn: () => verifyAddress(orderId, {}),
    onSuccess: () => invalidate(),
  });

  const confirmReleaseMutation = useMutation({
    mutationFn: () => confirmRelease(orderId, {}),
    onSuccess: () => invalidate(),
  });

  const updateOrderMutation = useMutation({
    // Persists the *effective* values (system defaults included) — so
    // saving an order that had no supplier writes the auto-selected sole
    // supplier, and one with no delivery date writes the birthday default.
    mutationFn: () =>
      updateOrder(orderId, {
        supplier_id: eff.supplierId ? Number(eff.supplierId) : null,
        delivery_date: eff.deliveryDate || null,
        catalogue_item_id: eff.catalogueId ? Number(eff.catalogueId) : null,
      }),
    onSuccess: () => {
      invalidate();
      setFulfilmentEdit({});
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
    verifyMutation.isPending ||
    confirmReleaseMutation.isPending ||
    updateOrderMutation.isPending ||
    deleteMutation.isPending;

  const supplierName = (id: number | null | undefined) =>
    id == null ? "Unassigned" : (suppliers.find((s) => s.id === id)?.name ?? `Supplier #${id}`);

  // "Dirty" = the effective values (which include system defaults like the
  // sole supplier / birthday delivery date) differ from what is actually
  // saved on the order — so "Save assignment" lights up when a default
  // needs persisting, not only after a manual edit.
  const fulfilmentDirty =
    eff.supplierId !== (order.supplier_id != null ? String(order.supplier_id) : "") ||
    eff.deliveryDate !== (order.delivery_date ?? "") ||
    eff.catalogueId !== (order.catalogue_item_id != null ? String(order.catalogue_item_id) : "");
  const catalogueItems = catalogueQuery.data ?? [];

  // "Verification is the approval" (plan §K): the Verify button is the
  // single routine happy-path action, available any time the address
  // isn't already VERIFIED. Manual Send/Resend remain for held orders and
  // exception recovery — mirrors birthday-api's order_email_service._send
  // reachability check exactly; this is a UX convenience only, never the
  // enforcement point.
  const canVerify = order.address_verification_status !== "VERIFIED" && !["CANCELLED", "COMPLETED"].includes(order.status);
  const canConfirmRelease = order.status === "REQUIRES_REVIEW";
  const canSendToSupplier =
    ["PENDING_VERIFICATION", "REQUIRES_ATTENTION"].includes(order.status) &&
    order.supplier_id != null &&
    order.address_verification_status === "VERIFIED";
  const canResend = ["REQUIRES_ATTENTION", "CHANGE_REQUESTED"].includes(order.status) && order.supplier_id != null;
  const verifyError = verifyMutation.error as Error | null;
  // Hard delete is PENDING_VERIFICATION-only and never-actioned (server is
  // the real boundary — see the 409 birthday-api returns otherwise).
  const canDelete = order.status === "PENDING_VERIFICATION";

  function submitAction() {
    if (actionOpen === "hold") holdMutation.mutate(reasonText);
    if (actionOpen === "release") releaseMutation.mutate(reasonText);
    if (actionOpen === "cancel") cancelMutation.mutate(reasonText);
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
              variant="primary"
              disabled={!canVerify || isMutating}
              loading={verifyMutation.isPending}
              onClick={() => verifyMutation.mutate()}
              title="The one routine checkpoint — marks the address VERIFIED and auto-releases a standard order to the supplier"
            >
              <BadgeCheck className="size-4" />
              Verify Address
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={!canConfirmRelease || isMutating}
              loading={confirmReleaseMutation.isPending}
              onClick={() => confirmReleaseMutation.mutate()}
              title="This order was flagged for a look before release — confirm to send it to the supplier"
            >
              Confirm &amp; Release
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

      {verifyError && (
        <div className="mb-6 rounded-xl border border-dt-danger/40 bg-dt-danger/5 p-3 text-sm text-dt-danger">
          Could not verify: {verifyError.message}.
        </div>
      )}

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
              <DetailRow label="Product" value="Cake" />
              <DetailRow label="Delivery Date" value={order.delivery_date ?? "—"} />
              <DetailRow label="Supplier" value={order.supplier_name ?? supplierName(order.supplier_id)} />
              <DetailRow label="Manual Override" value={order.is_manual_override ? "Yes" : "No"} />
              <DetailRow label="Verify By" value={order.verify_by ?? "—"} />
              {order.exception_reason && (
                <DetailRow label="Exception" value={<StatusBadge status="REQUIRES_ATTENTION" label={order.exception_reason} />} />
              )}
              <DetailRow
                label="Released"
                value={
                  order.released_at
                    ? `${new Date(order.released_at).toLocaleString()}${order.released_by ? "" : " · system (auto-released)"}`
                    : "Not yet released"
                }
              />
              <DetailRow label="Retry Count" value={order.retry_count} />
              {order.hold_reason && <DetailRow label="Hold Reason" value={order.hold_reason} />}
              {order.last_failure_reason && (
                <DetailRow label="Last Failure" value={order.last_failure_reason} />
              )}
            </CardContent>
          </Card>

          {scope?.isAdmin && (
            <Card>
              <CardHeader>
                <CardTitle>Fulfilment Assignment</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-3 text-sm text-dt-text-secondary">
                  The system pre-fills what it already knows — the only supplier (when there is just
                  one), the birthday as the delivery date, and Cake as the product. Adjust only where
                  an exception applies, then <strong>Save assignment</strong>.
                </p>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <FormField label="Supplier" htmlFor="fa-supplier">
                    <Select
                      id="fa-supplier"
                      value={eff.supplierId}
                      onChange={(e) =>
                        setFulfilmentEdit((f) => ({
                          ...f,
                          supplier_id: e.target.value,
                          // supplier changed → clear the variant, its catalogue no longer applies
                          catalogue_item_id: "",
                        }))
                      }
                    >
                      <option value="">Unassigned</option>
                      {suppliers.map((s) => (
                        <option key={s.id} value={String(s.id)}>
                          {s.name}
                          {s.status !== "ACTIVE" ? " (inactive)" : ""}
                          {s.is_default ? " · default" : ""}
                        </option>
                      ))}
                    </Select>
                    {order.supplier_id == null && eff.supplierId !== "" && (
                      <p className="mt-1 text-xs text-dt-text-secondary">
                        Auto-selected (only active supplier). Save to apply.
                      </p>
                    )}
                  </FormField>
                  <FormField label="Delivery Date" htmlFor="fa-date">
                    <input
                      id="fa-date"
                      type="date"
                      className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
                      value={eff.deliveryDate}
                      onChange={(e) =>
                        setFulfilmentEdit((f) => ({ ...f, delivery_date: e.target.value }))
                      }
                    />
                    {eff.deliveryDate === order.birthday_date && (
                      <p className="mt-1 text-xs text-dt-text-secondary">
                        Defaulted to the birthday — change for a weekend / holiday / supplier
                        constraint.
                      </p>
                    )}
                  </FormField>
                  <FormField label="Product" htmlFor="fa-product-type">
                    <input
                      id="fa-product-type"
                      value="Cake"
                      readOnly
                      className="w-full cursor-default rounded-lg border border-dt-border bg-dt-surface-warm/40 px-3 py-2 text-sm text-dt-text-primary"
                    />
                  </FormField>
                  {catalogueItems.length > 0 && (
                    <FormField label="Cake variant (optional)" htmlFor="fa-variant">
                      <Select
                        id="fa-variant"
                        value={eff.catalogueId}
                        onChange={(e) =>
                          setFulfilmentEdit((f) => ({ ...f, catalogue_item_id: e.target.value }))
                        }
                      >
                        <option value="">Standard cake (no specific variant)</option>
                        {catalogueItems
                          .filter((c) => c.is_active || String(c.id) === eff.catalogueId)
                          .map((c) => (
                            <option key={c.id} value={String(c.id)}>
                              {c.name}
                              {!c.is_active ? " (inactive)" : ""}
                            </option>
                          ))}
                      </Select>
                    </FormField>
                  )}
                </div>
                {updateOrderMutation.error && (
                  <p className="mt-2 text-sm text-dt-danger">
                    Could not save: {(updateOrderMutation.error as Error).message}
                  </p>
                )}
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    disabled={!fulfilmentDirty || isMutating}
                    loading={updateOrderMutation.isPending}
                    onClick={() => updateOrderMutation.mutate()}
                  >
                    Save assignment
                  </Button>
                  {fulfilmentDirty && (
                    <Button size="sm" variant="secondary" onClick={() => setFulfilmentEdit({})}>
                      Discard changes
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Address Verification</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-dt-text-secondary">
                P&C-manual only — set this after confirming the delivery address directly with the
                team member. Nothing here contacts the team member automatically. This is the one
                routine checkpoint: use the <strong>Verify Address</strong> button above once
                confirmed — a standard order releases to the supplier immediately, a flagged one
                (e.g. a corrected address) moves to a quick review instead.
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
              variant={actionOpen === "cancel" ? "danger" : "primary"}
              size="sm"
              loading={isMutating}
              disabled={actionOpen === "hold" && reasonText.trim() === ""}
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
