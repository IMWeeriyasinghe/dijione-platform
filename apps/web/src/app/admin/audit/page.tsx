"use client";

import { useQuery } from "@tanstack/react-query";
import { listAdminAudit } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Table, Thead, Th, Tr, Td } from "@/components/ui/Table";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/States";
import { formatDateTime } from "@/lib/utils";

export default function AdminAuditPage() {
  const query = useQuery({ queryKey: ["admin", "audit"], queryFn: () => listAdminAudit({ limit: 200 }) });

  return (
    <div>
      <PageHeader
        title="Audit"
        description="Every administrative change — user activation, platform role changes, module assignment, and client scope changes — with actor, timestamp, and before/after state."
      />
      {query.isLoading && <LoadingState label="Loading audit history…" />}
      {query.isError && <ErrorState message="Could not load the audit log." onRetry={() => query.refetch()} />}
      {query.data && query.data.length === 0 && <EmptyState title="No audit events yet" />}
      {query.data && query.data.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>When</Th>
              <Th>Actor</Th>
              <Th>Action</Th>
              <Th>Entity</Th>
              <Th>Details</Th>
            </tr>
          </Thead>
          <tbody>
            {query.data.map((e) => (
              <Tr key={e.id}>
                <Td className="whitespace-nowrap text-sm text-dt-text-secondary">{formatDateTime(e.created_at)}</Td>
                <Td className="text-sm">{e.actor_name ?? "System"}</Td>
                <Td>
                  <code className="rounded bg-dt-surface-warm px-1.5 py-0.5 text-xs">{e.action}</code>
                </Td>
                <Td className="text-sm text-dt-text-secondary">
                  {e.entity_type} #{e.entity_id}
                </Td>
                <Td className="max-w-xs truncate text-xs text-dt-text-secondary" title={e.new_state}>
                  {e.new_state || e.previous_state || "—"}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
