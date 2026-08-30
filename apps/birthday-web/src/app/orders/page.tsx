"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { listOrders } from "@/lib/api";
import {
  ADDRESS_VERIFICATION_STATUSES,
  LEAD_TIME_CLASSES,
  ORDER_STATUSES,
} from "@dijione/contracts";
import {
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Pagination,
  PageHeader,
  SearchInput,
  Select,
  SortableTh,
  StatusBadge,
  Table,
  Td,
  Thead,
  Tr,
  useSortToggle,
  type SortDirection,
} from "@dijione/design-system";

// Imported from @dijione/contracts (semi-automation future-state plan §P)
// instead of a locally re-declared literal array — this was one of the
// ~20 places the status set used to be independently typed.
const STATUS_OPTIONS = ORDER_STATUSES;
const LEAD_TIME_OPTIONS = LEAD_TIME_CLASSES;
const ADDRESS_STATUS_OPTIONS = ADDRESS_VERIFICATION_STATUSES;

const PAGE_SIZE = 20;

export default function OrdersPage() {
  // Dashboard attention cards deep-link here with a pre-set filter (plan
  // §M/§36 — "avoid static KPI cards with no action") — read it once on
  // load so /orders?status_filter=REQUIRES_ATTENTION actually filters.
  const searchParams = useSearchParams();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status_filter") ?? "");
  const [leadTimeClass, setLeadTimeClass] = useState("");
  const [officeLocation, setOfficeLocation] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [addressStatus, setAddressStatus] = useState("");
  const [sortBy, setSortBy] = useState<string | null>(searchParams.get("sort_by"));
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [page, setPage] = useState(1);

  const params = {
    search: search || undefined,
    status_filter: statusFilter || undefined,
    lead_time_class: leadTimeClass || undefined,
    office_location: officeLocation || undefined,
    supplier_id: supplierId ? Number(supplierId) : undefined,
    address_verification_status: addressStatus || undefined,
    sort_by: sortBy || undefined,
    sort_direction: sortDirection,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["birthday-orders", params],
    queryFn: () => listOrders(params),
  });

  const toggleSort = useSortToggle(sortBy, sortDirection, setSortBy, setSortDirection);

  function resetAndSet<T>(setter: (v: T) => void, value: T) {
    setPage(1);
    setter(value);
  }

  const orders = data?.items ?? [];

  return (
    <div>
      <PageHeader title="Cake Orders" description="Register of every cake order tracked by DijiBirthday." />

      <div className="mb-4 space-y-3">
        <SearchInput
          value={search}
          onChange={(v) => resetAndSet(setSearch, v)}
          placeholder="Search team member ID, name, or order reference…"
          className="max-w-md"
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <FormField label="Status" htmlFor="status-filter">
            <Select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => resetAndSet(setStatusFilter, e.target.value)}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField label="Lead Time Class" htmlFor="lead-time-filter">
            <Select
              id="lead-time-filter"
              value={leadTimeClass}
              onChange={(e) => resetAndSet(setLeadTimeClass, e.target.value)}
            >
              <option value="">All classes</option>
              {LEAD_TIME_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField label="Address Verification" htmlFor="address-filter">
            <Select
              id="address-filter"
              value={addressStatus}
              onChange={(e) => resetAndSet(setAddressStatus, e.target.value)}
            >
              <option value="">All</option>
              {ADDRESS_STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField label="Office Location" htmlFor="office-filter">
            <Input
              id="office-filter"
              placeholder="e.g. Colombo"
              value={officeLocation}
              onChange={(e) => resetAndSet(setOfficeLocation, e.target.value)}
            />
          </FormField>

          <FormField label="Supplier ID" htmlFor="supplier-filter">
            <Input
              id="supplier-filter"
              type="number"
              placeholder="e.g. 1"
              value={supplierId}
              onChange={(e) => resetAndSet(setSupplierId, e.target.value)}
            />
          </FormField>
        </div>
      </div>

      {isLoading ? (
        <LoadingState label="Loading orders…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : orders.length === 0 ? (
        <EmptyState title="No orders found" description="Try adjusting the search or filters above." />
      ) : (
        <>
          <Table>
            <Thead>
              <Tr>
                <SortableTh
                  label="Reference"
                  sortKey="employee_number"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Team Member"
                  sortKey="employee_name"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Birthday"
                  sortKey="birthday_date"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Delivery Date"
                  sortKey="delivery_date"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Supplier"
                  sortKey="supplier_id"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Status"
                  sortKey="status"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
              </Tr>
            </Thead>
            <tbody>
              {orders.map((order) => (
                <Tr key={order.id}>
                  <Td>
                    <Link href={`/orders/${order.id}`} className="font-medium text-dt-text-primary hover:underline">
                      {order.order_reference}
                    </Link>
                    {order.requires_admin_review && (
                      <p className="text-xs font-medium text-dt-warning">Needs review</p>
                    )}
                  </Td>
                  <Td>
                    {order.employee_name}
                    <p className="text-xs text-dt-text-secondary">
                      {order.employee_number ?? (
                        <span className="italic text-dt-text-secondary/70">
                          {order.employee_id} (internal id — no team member ID)
                        </span>
                      )}
                    </p>
                  </Td>
                  <Td>{order.birthday_date}</Td>
                  <Td>{order.delivery_date ?? "—"}</Td>
                  <Td>{order.supplier_name ?? (order.supplier_id != null ? `Supplier #${order.supplier_id}` : "Unassigned")}</Td>
                  <Td>
                    <StatusBadge status={order.status} />
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
