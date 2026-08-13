"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { listAdminModules, listAdminUsers } from "@/lib/api";
import { PLATFORM_ROLE_LABELS } from "@dijione/contracts";
import {
  Avatar,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
  formatDateTime,
} from "@dijione/design-system";

const PLATFORM_ROLE_OPTIONS = ["PLATFORM_USER", "PLATFORM_ADMIN", "SUPER_ADMIN"];

export default function AdminUsersPage() {
  const query = useQuery({ queryKey: ["admin", "users"], queryFn: listAdminUsers });
  const modulesQuery = useQuery({ queryKey: ["admin", "modules"], queryFn: listAdminModules });
  const [search, setSearch] = useState("");
  const [appFilter, setAppFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");

  const filtered = useMemo(() => {
    const data = query.data ?? [];
    return data.filter((u) => {
      if (search.trim()) {
        const q = search.trim().toLowerCase();
        if (!u.full_name.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q)) return false;
      }
      if (appFilter && !u.module_assignments.some((m) => m.enabled && m.module_key === appFilter)) return false;
      if (roleFilter && u.platform_role !== roleFilter) return false;
      if (activeFilter === "active" && !u.is_active) return false;
      if (activeFilter === "inactive" && u.is_active) return false;
      return true;
    });
  }, [query.data, search, appFilter, roleFilter, activeFilter]);

  return (
    <div>
      <PageHeader
        title="Users"
        description="Every DijiOne identity, platform role, and module access — activate/deactivate, assign platform roles, and manage module access from a user's detail page."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name or email…"
          className="w-64"
        />
        <Select value={appFilter} onChange={(e) => setAppFilter(e.target.value)} className="max-w-xs">
          <option value="">All Applications</option>
          {(modulesQuery.data ?? []).map((m) => (
            <option key={m.key} value={m.key}>
              {m.name}
            </option>
          ))}
        </Select>
        <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="max-w-xs">
          <option value="">All Platform Roles</option>
          {PLATFORM_ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {PLATFORM_ROLE_LABELS[r]}
            </option>
          ))}
        </Select>
        <Select value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)} className="max-w-xs">
          <option value="">Active &amp; Inactive</option>
          <option value="active">Active only</option>
          <option value="inactive">Inactive only</option>
        </Select>
      </div>

      {query.isLoading && <LoadingState label="Loading users…" />}
      {query.isError && <ErrorState message="Could not load users." onRetry={() => query.refetch()} />}
      {query.data && filtered.length === 0 && <EmptyState title="No users found" description="Try adjusting your search or filters." />}
      {query.data && filtered.length > 0 && (
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
            {filtered.map((u) => (
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
                    href={`/users/${u.id}`}
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
