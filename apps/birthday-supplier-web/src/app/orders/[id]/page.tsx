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
  StatusBadge,
  Textarea,
} from "@dijione/design-system";
import { acknowledgePortalOrder, getPortalOrder, raisePortalIssue, updatePortalOrderStatus } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

// Allow-listed status progressions a supplier may set directly — mirrors
// birthday-api's portal router `_SUPPLIER_ALLOWED_TARGETS` exactly; the
// server re-validates regardless, this only drives which buttons show.
const NEXT_STATUS_OPTIONS: Record<string, { value: string; label: string }[]> = {
  SUPPLIER_REVIEW: [
    { value: "CONFIRMED", label: "Confirm / Accept" },
    { value: "CHANGE_REQUESTED", label: "Request Change" },
    { value: "UNABLE_TO_FULFIL", label: "Unable to Fulfil" },
  ],
  CONFIRMED: [{ value: "PREPARING", label: "Start Preparing" }],
  PREPARING: [{ value: "OUT_FOR_DELIVERY", label: "Out for Delivery" }],
  OUT_FOR_DELIVERY: [{ value: "DELIVERED", label: "Mark Delivered" }],
};

export default function SupplierOrderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const orderId = Number(id);
  const { token } = useSupplierAuth();
  const queryClient = useQueryClient();
  const [issueOpen, setIssueOpen] = useState(false);
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

  const ackMutation = useMutation({
    mutationFn: () => acknowledgePortalOrder(token!, orderId),
    onSuccess: invalidate,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => updatePortalOrderStatus(token!, orderId, status),
    onSuccess: invalidate,
  });

  const issueMutation = useMutation({
    mutationFn: () => raisePortalIssue(token!, orderId, issueText),
    onSuccess: () => {
      invalidate();
      setIssueOpen(false);
      setIssueText("");
    },
  });

  if (isLoading) return <LoadingState label="Loading order…" />;
  if (isError || !order) return <ErrorState onRetry={() => refetch()} />;

  const nextOptions = NEXT_STATUS_OPTIONS[order.status] ?? [];
  const canAcknowledge = order.status === "SENT_TO_SUPPLIER";

  return (
    <div>
      <Link href="/" className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary">
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
          {canAcknowledge && (
            <Button size="sm" loading={ackMutation.isPending} onClick={() => ackMutation.mutate()}>
              <CheckCircle2 className="size-4" />
              Acknowledge
            </Button>
          )}
          {nextOptions.map((opt) => (
            <Button
              key={opt.value}
              size="sm"
              variant={opt.value === "UNABLE_TO_FULFIL" ? "danger" : "secondary"}
              loading={statusMutation.isPending}
              onClick={() => statusMutation.mutate(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
          <Button size="sm" variant="secondary" onClick={() => setIssueOpen(true)}>
            <TriangleAlert className="size-4" />
            Raise Issue
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

      <Modal open={issueOpen} onClose={() => setIssueOpen(false)} title="Raise an Issue">
        <div className="flex flex-col gap-4">
          <FormField label="Issue detail" htmlFor="issue-detail" required>
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
