"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Pagination,
  SearchInput,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import { listPortalOrders } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

const PAGE_SIZE = 20;

export default function SupplierOrdersPage() {
  const { token } = useSupplierAuth();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const params = { search: search || undefined, page, page_size: PAGE_SIZE };
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["portal-orders", params],
    queryFn: () => listPortalOrders(token!, params),
    enabled: !!token,
  });

  const orders = data?.items ?? [];

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Your Orders</h2>
        <p className="text-sm text-dt-text-secondary">
          Cake orders assigned to your business. Only fulfilment details are shown here.
        </p>
      </div>

      <SearchInput
        value={search}
        onChange={(v) => {
          setPage(1);
          setSearch(v);
        }}
        placeholder="Search order reference or recipient…"
        className="mb-4 max-w-md"
      />

      {isLoading ? (
        <LoadingState label="Loading orders…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : orders.length === 0 ? (
        <EmptyState title="No orders yet" description="Orders will appear here once approved and sent to you." />
      ) : (
        <>
          <Table>
            <Thead>
              <Tr>
                <Th>Reference</Th>
                <Th>Recipient</Th>
                <Th>Delivery Date</Th>
                <Th>Location</Th>
                <Th>Product</Th>
                <Th>Qty</Th>
                <Th>Address Verified</Th>
                <Th>Status</Th>
              </Tr>
            </Thead>
            <tbody>
              {orders.map((order) => (
                <Tr key={order.id}>
                  <Td>
                    <Link href={`/orders/${order.id}`} className="font-medium text-dt-text-primary hover:underline">
                      {order.order_reference}
                    </Link>
                  </Td>
                  <Td>{order.employee_name}</Td>
                  <Td>{order.delivery_date ?? "—"}</Td>
                  <Td>{order.office_location}</Td>
                  <Td>{order.catalogue_item_name ?? "—"}</Td>
                  <Td>{order.quantity}</Td>
                  <Td>{order.address_verified ? "Yes" : "No"}</Td>
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
