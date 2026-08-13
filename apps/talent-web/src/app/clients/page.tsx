"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import Link from "next/link";
import { listClientPortfolios } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Table, Thead, Th, Tr, Td } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";

export default function ClientPortfoliosPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["client-portfolios"],
    queryFn: listClientPortfolios,
  });

  return (
    <div>
      <PageHeader title="Client Portfolios" description="Every Dijital Team client tracked in DijiTalentFlow." />

      {isLoading && <LoadingState label="Loading clients…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && <EmptyState icon={Building2} title="No clients yet" />}

      {data && data.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>Client</Th>
              <Th>Industry</Th>
              <Th>Account Manager</Th>
              <Th>Total Requests</Th>
              <Th>Active Requests</Th>
              <Th>Status</Th>
            </tr>
          </Thead>
          <tbody>
            {data.map((c) => (
              <Tr key={c.id}>
                <Td className="font-medium">
                  <Link href={`/clients/${c.id}`} className="hover:text-dt-burnt-orange">
                    {c.name}
                  </Link>
                </Td>
                <Td>{c.industry || "—"}</Td>
                <Td>{c.account_manager || "—"}</Td>
                <Td>{c.total_requests}</Td>
                <Td>{c.active_requests}</Td>
                <Td>
                  <StatusBadge status={c.status} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
