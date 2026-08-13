"use client";

import { useQuery } from "@tanstack/react-query";
import { listAdminRoles } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Table, Thead, Th, Tr, Td } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { LoadingState, ErrorState } from "@dijione/design-system";

export default function AdminRolesPage() {
  const query = useQuery({ queryKey: ["admin", "roles"], queryFn: listAdminRoles });

  return (
    <div>
      <PageHeader
        title="Roles"
        description="Named permission bundles. Platform roles apply DijiOne-wide; module roles apply within one application. System roles are protected from deletion."
      />
      {query.isLoading && <LoadingState label="Loading roles…" />}
      {query.isError && <ErrorState message="Could not load roles." onRetry={() => query.refetch()} />}
      {query.data && (
        <Table>
          <Thead>
            <tr>
              <Th>Role</Th>
              <Th>Scope</Th>
              <Th>Description</Th>
              <Th>Permissions</Th>
              <Th>Users</Th>
            </tr>
          </Thead>
          <tbody>
            {query.data.map((r) => (
              <Tr key={r.id}>
                <Td className="font-medium">{r.name}</Td>
                <Td>
                  <StatusBadge status={r.module_key ?? "PLATFORM"} label={r.module_key ?? "Platform"} />
                </Td>
                <Td className="max-w-sm text-sm text-dt-text-secondary">{r.description}</Td>
                <Td>{r.permission_count}</Td>
                <Td>{r.user_count}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
