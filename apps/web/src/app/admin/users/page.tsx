"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { listAdminUsers } from "@/lib/api";
import { PLATFORM_ROLE_LABELS } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Table, Thead, Th, Tr, Td } from "@/components/ui/Table";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Avatar } from "@/components/ui/Avatar";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui/States";
import { formatDateTime } from "@/lib/utils";

export default function AdminUsersPage() {
  const query = useQuery({ queryKey: ["admin", "users"], queryFn: listAdminUsers });

  return (
    <div>
      <PageHeader
        title="Users"
        description="Every DijiOne identity, platform role, and module access — activate/deactivate, assign platform roles, and manage module access from a user's detail page."
      />
      {query.isLoading && <LoadingState label="Loading users…" />}
      {query.isError && <ErrorState message="Could not load users." onRetry={() => query.refetch()} />}
      {query.data && query.data.length === 0 && <EmptyState title="No users found" />}
      {query.data && query.data.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>User</Th>
              <Th>Platform Role</Th>
              <Th>Applications</Th>
              <Th>Status</Th>
              <Th>Last Login</Th>
              <Th />
            </tr>
          </Thead>
          <tbody>
            {query.data.map((u) => (
              <Tr key={u.id}>
                <Td>
                  <div className="flex items-center gap-3">
                    <Avatar name={u.full_name} size={32} />
                    <div className="min-w-0">
                      <p className="font-medium text-dt-text-primary">{u.full_name}</p>
                      <p className="truncate text-xs text-dt-text-secondary">{u.email}</p>
                    </div>
                  </div>
                </Td>
                <Td>
                  <StatusBadge
                    status={u.platform_role}
                    label={PLATFORM_ROLE_LABELS[u.platform_role] ?? u.platform_role}
                  />
                </Td>
                <Td>
                  <span className="text-sm text-dt-text-secondary">
                    {u.module_assignments.filter((m) => m.enabled).map((m) => m.module_name).join(", ") || "None"}
                  </span>
                </Td>
                <Td>
                  <StatusBadge status={u.is_active ? "ACTIVE_CLIENT" : "CANCELLED"} label={u.is_active ? "Active" : "Inactive"} />
                </Td>
                <Td>
                  <span className="text-sm text-dt-text-secondary">
                    {u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}
                  </span>
                </Td>
                <Td>
                  <Link
                    href={`/admin/users/${u.id}`}
                    className="flex items-center gap-1 text-sm font-medium text-dt-burnt-orange"
                  >
                    Manage <ChevronRight className="size-3.5" />
                  </Link>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
