"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Pagination,
  SearchInput,
  Select,
  SortableTh,
  StatusBadge,
  Table,
  Th,
  Td,
  Thead,
  Tr,
  useSortToggle,
  type SortDirection,
} from "@dijione/design-system";
import { getSupplierOrderStatusLabel } from "@dijione/contracts";
import { listPortalOrders } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

const PAGE_SIZE = 20;

// Statuses a supplier can ever see (mirrors order_status_service.SUPPLIER_VISIBLE_STATUSES).
const STATUS_OPTIONS = [
  "SENT_TO_SUPPLIER",
  "CHANGE_REQUESTED",
  "CONFIRMED",
  "PREPARING",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "COMPLETED",
  "UNABLE_TO_FULFIL",
  "CANCELLED",
] as const;

const TERMINAL = new Set(["DELIVERED", "COMPLETED", "CANCELLED", "UNABLE_TO_FULFIL"]);

export default function SupplierOrdersPage() {
  const { token } = useSupplierAuth();
  const router = useRouter();
  // Phase 1.6 §11 (R16) — the fix for the root cause of "every dashboard
  // tile lands on the unfiltered list": this page never read the URL at
  // all. Seed every filter's initial state from the query string the
  // dashboard cards actually link with.
  const searchParams = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status_filter") ?? "");
  const [due, setDue] = useState(searchParams.get("due") ?? "");
  const [hasOpenIssue, setHasOpenIssue] = useState(searchParams.get("has_open_issue") === "true");
  const [completed, setCompleted] = useState(searchParams.get("completed") ?? "");
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);

  const toggleSort = useSortToggle(sortBy, sortDirection, setSortBy, setSortDirection);

  function resetAndSet<T>(setter: (v: T) => void, value: T) {
    setPage(1);
    setter(value);
  }

  const params = {
    search: search || undefined,
    status_filter: statusFilter || undefined,
    due: (due || undefined) as "today" | "tomorrow" | "overdue" | undefined,
    has_open_issue: hasOpenIssue || undefined,
    completed: (completed || undefined) as "today" | undefined,
    sort_by: sortBy || undefined,
    sort_direction: sortDirection,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["portal-orders", params],
    queryFn: () => listPortalOrders(token!, params),
    enabled: !!token,
  });

  const orders = data?.items ?? [];
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Your Orders</h2>
        <p className="text-sm text-dt-text-secondary">
          Cake orders assigned to your business. Only fulfilment details are shown here.
        </p>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <SearchInput
          value={search}
          onChange={(v) => resetAndSet(setSearch, v)}
          placeholder="Search order reference or recipient…"
          className="max-w-xs flex-1"
        />
        <Select
          value={statusFilter}
          onChange={(e) => resetAndSet(setStatusFilter, e.target.value)}
          className="w-auto"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {getSupplierOrderStatusLabel(s)}
            </option>
          ))}
        </Select>
        <Select value={due} onChange={(e) => resetAndSet(setDue, e.target.value)} className="w-auto">
          <option value="">Any due date</option>
          <option value="today">Due today</option>
          <option value="tomorrow">Due tomorrow</option>
          <option value="overdue">Overdue</option>
        </Select>
        <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
          <input
            type="checkbox"
            checked={hasOpenIssue}
            onChange={(e) => resetAndSet(setHasOpenIssue, e.target.checked)}
          />
          Open problems only
        </label>
        <Select
          value={completed}
          onChange={(e) => resetAndSet(setCompleted, e.target.value)}
          className="w-auto"
        >
          <option value="">Any completion</option>
          <option value="today">Completed today</option>
        </Select>
      </div>

      {isLoading ? (
        <LoadingState label="Loading orders…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : orders.length === 0 ? (
        <EmptyState title="No orders" description="Nothing matches the current search / filters." />
      ) : (
        <>
          <Table>
            <Thead>
              <Tr>
                <SortableTh label="Reference" sortKey="order_reference" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
                <SortableTh label="Recipient" sortKey="employee_name" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
                <SortableTh label="Delivery Date" sortKey="delivery_date" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
                <Th>Location</Th>
                <Th>Product</Th>
                <Th>Qty</Th>
                <Th>Address Verified</Th>
                <SortableTh label="Status" sortKey="status" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
              </Tr>
            </Thead>
            <tbody>
              {orders.map((order) => (
                <Tr
                  key={order.id}
                  className="cursor-pointer transition hover:bg-dt-surface-warm"
                  onClick={() => router.push(`/orders/${order.id}`)}
                >
                  <Td className="font-medium text-dt-text-primary">{order.order_reference}</Td>
                  <Td>{order.employee_name}</Td>
                  <Td>
                    {order.delivery_date ?? "—"}
                    {order.delivery_date &&
                      order.delivery_date < today &&
                      !TERMINAL.has(order.status) && (
                        <span className="ml-2 rounded-full bg-dt-danger/10 px-2 py-0.5 text-[11px] font-medium text-dt-danger">
                          Overdue
                        </span>
                      )}
                  </Td>
                  <Td>{order.office_location}</Td>
                  <Td>{order.catalogue_item_name ?? "—"}</Td>
                  <Td>{order.quantity}</Td>
                  <Td>{order.address_verified ? "Yes" : "No"}</Td>
                  <Td>
                    <StatusBadge status={order.status} label={getSupplierOrderStatusLabel(order.status)} />
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
