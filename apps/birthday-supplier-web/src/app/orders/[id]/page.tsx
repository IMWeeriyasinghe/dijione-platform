"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
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
import { SUPPLIER_DRIVABLE_TARGETS, type OrderIssueType } from "@dijione/contracts";
import { acceptPortalOrder, getPortalOrder, raisePortalIssue, updatePortalOrderStatus } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

// Labels for the transitions a supplier may set directly. The allow-list
// itself is imported from @dijione/contracts — derived from the backend's
// order_status_service.SUPPLIER_DRIVABLE, not a second hand-typed copy
// (the drift that motivated this: this file used to re-declare the whole
// table "mirrors ... exactly" with nothing enforcing the mirror).
const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: "Confirm / Accept",
  CHANGE_REQUESTED: "Request Change",
  UNABLE_TO_FULFIL: "Unable to Fulfil",
  PREPARING: "Start Preparing",
  OUT_FOR_DELIVERY: "Out for Delivery",
  DELIVERED: "Mark Delivered",
};

const ISSUE_TYPE_OPTIONS: { value: OrderIssueType; label: string }[] = [
  { value: "CHANGE_REQUEST", label: "Request a change" },
  { value: "CANNOT_FULFIL", label: "Cannot fulfil this order" },
  { value: "DELIVERY_ISSUE", label: "Delivery problem" },
  { value: "OTHER", label: "Other" },
];

export default function SupplierOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const orderId = Number(id);
  const { token } = useSupplierAuth();
  const queryClient = useQueryClient();
  const [issueOpen, setIssueOpen] = useState(false);
  const [issueType, setIssueType] = useState<OrderIssueType>("OTHER");
  const [issueText, setIssueText] = useState("");

  const { data: order, isLoading, isError, refetch } = useQuery({
    queryKey: ["portal-order", orderId],
    queryFn: () => getPortalOrder(token!, orderId),
    enabled: !!token,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portal-order", orderId] });
    queryClient.invalidateQueries({ queryKey: ["portal-orders"] });
  };

  // Merged acknowledge+confirm (plan §O) — one commitment, one click:
  // "we have it and we will fulfil it."
  const acceptMutation = useMutation({
    mutationFn: () => acceptPortalOrder(token!, orderId),
    onSuccess: invalidate,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => updatePortalOrderStatus(token!, orderId, status),
    onSuccess: invalidate,
  });

  const issueMutation = useMutation({
    mutationFn: () => raisePortalIssue(token!, orderId, issueType, issueText),
    onSuccess: () => {
      invalidate();
      setIssueOpen(false);
      setIssueText("");
      setIssueType("OTHER");
    },
  });

  if (isLoading) return <LoadingState label="Loading order…" />;
  if (isError || !order) return <ErrorState onRetry={() => refetch()} />;

  // CONFIRMED is reached via the Accept button below, not a status pill —
  // avoids showing "Confirm / Accept" twice for the same transition.
  const nextOptions = (SUPPLIER_DRIVABLE_TARGETS[order.status] ?? []).filter((s) => s !== "CONFIRMED");
  const canAccept = order.status === "SENT_TO_SUPPLIER";

  return (
    <div>
      <Link href="/orders" className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary">
        <ArrowLeft className="size-4" />
        Back to orders
      </Link>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-dt-border bg-dt-surface p-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-dt-text-primary">{order.order_reference}</h1>
            <StatusBadge status={order.status} />
          </div>
          <p className="mt-1 text-sm text-dt-text-secondary">
            {order.employee_name} · {order.office_location}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canAccept && (
            <Button size="sm" loading={acceptMutation.isPending} onClick={() => acceptMutation.mutate()}>
              <CheckCircle2 className="size-4" />
              Accept
            </Button>
          )}
          {nextOptions.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={value === "UNABLE_TO_FULFIL" ? "danger" : "secondary"}
              loading={statusMutation.isPending}
              onClick={() => statusMutation.mutate(value)}
            >
              {STATUS_LABELS[value] ?? value}
            </Button>
          ))}
          <Button size="sm" variant="secondary" onClick={() => setIssueOpen(true)}>
            <TriangleAlert className="size-4" />
            Report a Problem
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Fulfilment Details</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
              Delivery Date
            </span>
            <p className="text-sm text-dt-text-primary">{order.delivery_date ?? "Not yet set"}</p>
          </div>
          <div>
            <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Product</span>
            <p className="text-sm text-dt-text-primary">{order.catalogue_item_name ?? "Not specified"}</p>
          </div>
          <div>
            <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Quantity</span>
            <p className="text-sm text-dt-text-primary">{order.quantity}</p>
          </div>
          <div>
            <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
              Address Verified
            </span>
            <p className="text-sm text-dt-text-primary">{order.address_verified ? "Yes" : "No"}</p>
          </div>
          <div className="sm:col-span-2">
            <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
              Delivery Address
            </span>
            {order.address_verified && order.delivery_address_line1 ? (
              <address className="mt-1 text-sm not-italic text-dt-text-primary">
                {order.delivery_address_line1}
                {order.delivery_address_line2 && (
                  <>
                    <br />
                    {order.delivery_address_line2}
                  </>
                )}
                <br />
                {[order.delivery_city, order.delivery_state_province, order.delivery_postal_code]
                  .filter(Boolean)
                  .join(", ")}
                {order.delivery_country && (
                  <>
                    <br />
                    {order.delivery_country}
                  </>
                )}
              </address>
            ) : (
              <p className="mt-1 text-sm text-dt-text-secondary">
                Released once the delivery address has been verified by Dijital Team.
              </p>
            )}
          </div>
          {order.special_instructions.length > 0 && (
            <div className="sm:col-span-2">
              <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
                Special Instructions
              </span>
              <ul className="mt-1 list-disc pl-5 text-sm text-dt-text-primary">
                {order.special_instructions.map((instr, i) => (
                  <li key={i}>{instr}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Modal open={issueOpen} onClose={() => setIssueOpen(false)} title="Report a Problem">
        <div className="flex flex-col gap-4">
          <FormField label="What's the problem?" htmlFor="issue-type" required>
            <Select id="issue-type" value={issueType} onChange={(e) => setIssueType(e.target.value as OrderIssueType)}>
              {ISSUE_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Detail" htmlFor="issue-detail" required>
            <Textarea
              id="issue-detail"
              value={issueText}
              onChange={(e) => setIssueText(e.target.value)}
              placeholder="e.g. Out of stock for this cake size"
            />
          </FormField>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIssueOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={issueMutation.isPending}
              disabled={issueText.trim() === ""}
              onClick={() => issueMutation.mutate()}
            >
              Submit
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
