"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ShieldAlert } from "lucide-react";
import Link from "next/link";
import {
  ApiError,
  getAdminUser,
  getEffectiveAccess,
  listAdminClients,
  listAdminModules,
  listAdminRoles,
  updatePlatformRole,
  updateUserStatus,
  upsertModuleAssignment,
} from "@/lib/api";
import { PLATFORM_ROLE_LABELS } from "@dijione/contracts";
import { Card } from "@dijione/design-system";
import { Button } from "@dijione/design-system";
import { Select } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { Avatar } from "@dijione/design-system";
import { LoadingState, ErrorState } from "@dijione/design-system";
import { formatDateTime } from "@dijione/design-system";

const PLATFORM_ROLE_OPTIONS = ["PLATFORM_USER", "PLATFORM_ADMIN", "SUPER_ADMIN"];

function useUserQueries(userId: number) {
  const userQuery = useQuery({ queryKey: ["admin", "users", userId], queryFn: () => getAdminUser(userId) });
  const rolesQuery = useQuery({ queryKey: ["admin", "roles"], queryFn: listAdminRoles });
  const modulesQuery = useQuery({ queryKey: ["admin", "modules"], queryFn: listAdminModules });
  const clientsQuery = useQuery({ queryKey: ["admin", "clients"], queryFn: listAdminClients });
  const effectiveQuery = useQuery({
    queryKey: ["admin", "users", userId, "effective-access"],
    queryFn: () => getEffectiveAccess(userId),
  });
  return { userQuery, rolesQuery, modulesQuery, clientsQuery, effectiveQuery };
}

function ModuleAssignmentEditor({
  userId,
  moduleKey,
  moduleName,
  moduleStatus,
  availableRoles,
  clients,
  current,
  onSaved,
}: {
  userId: number;
  moduleKey: string;
  moduleName: string;
  moduleStatus: string;
  availableRoles: { key: string; name: string }[];
  clients: { id: number; name: string }[];
  current: { role: string; enabled: boolean; all_clients: boolean; client_ids: number[] } | undefined;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState(current?.enabled ?? false);
  const [role, setRole] = useState(current?.role ?? availableRoles[0]?.key ?? "");
  const [allClients, setAllClients] = useState(current?.all_clients ?? true);
  const [clientIds, setClientIds] = useState<number[]>(current?.client_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      upsertModuleAssignment(userId, moduleKey, {
        role,
        enabled,
        client_scope: { all_clients: allClients, client_ids: allClients ? [] : clientIds },
      }),
    onSuccess: () => {
      setError(null);
      onSaved();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not save this module assignment."),
  });

  if (availableRoles.length === 0) {
    return (
      <Card className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-dt-text-primary">{moduleName}</p>
            <p className="mt-1 text-sm text-dt-text-secondary">
              No functional roles are defined for this module yet.
            </p>
          </div>
          <StatusBadge status={moduleStatus} />
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="font-semibold text-dt-text-primary">{moduleName}</p>
        <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-dt-text-primary">Role</label>
          <Select value={role} onChange={(e) => setRole(e.target.value)} disabled={!enabled}>
            {availableRoles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-dt-text-primary">Client Scope</label>
          <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
            <input
              type="checkbox"
              checked={allClients}
              onChange={(e) => setAllClients(e.target.checked)}
              disabled={!enabled}
            />
            All Clients
          </label>
        </div>
      </div>

      {!allClients && (
        <div className="mt-3 flex flex-wrap gap-3 rounded-lg border border-dt-border bg-dt-surface-warm p-3">
          {clients.map((c) => (
            <label key={c.id} className="flex items-center gap-1.5 text-sm text-dt-text-primary">
              <input
                type="checkbox"
                checked={clientIds.includes(c.id)}
                disabled={!enabled}
                onChange={(e) =>
                  setClientIds((prev) =>
                    e.target.checked ? [...prev, c.id] : prev.filter((id) => id !== c.id)
                  )
                }
              />
              {c.name}
            </label>
          ))}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-dt-danger">{error}</p>}

      <div className="mt-4">
        <Button size="sm" onClick={() => mutation.mutate()} loading={mutation.isPending}>
          Save {moduleName} Access
        </Button>
      </div>
    </Card>
  );
}

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const userId = Number(params.id);
  const queryClient = useQueryClient();
  const { userQuery, rolesQuery, modulesQuery, clientsQuery, effectiveQuery } = useUserQueries(userId);
  const [statusError, setStatusError] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  };

  const statusMutation = useMutation({
    mutationFn: (is_active: boolean) => updateUserStatus(userId, is_active),
    onSuccess: () => {
      setStatusError(null);
      invalidate();
    },
    onError: (e: unknown) => setStatusError(e instanceof ApiError ? e.message : "Could not update status."),
  });

  const roleMutation = useMutation({
    mutationFn: (platform_role: string) => updatePlatformRole(userId, platform_role),
    onSuccess: () => {
      setStatusError(null);
      invalidate();
    },
    onError: (e: unknown) => setStatusError(e instanceof ApiError ? e.message : "Could not update platform role."),
  });

  if (userQuery.isLoading || rolesQuery.isLoading || modulesQuery.isLoading || clientsQuery.isLoading) {
    return <LoadingState label="Loading user…" />;
  }
  if (userQuery.isError || !userQuery.data) {
    return <ErrorState message="Could not load this user." onRetry={() => router.refresh()} />;
  }

  const user = userQuery.data;
  const roles = rolesQuery.data ?? [];
  const modules = modulesQuery.data ?? [];
  const clients = clientsQuery.data ?? [];

  return (
    <div>
      <Link href="/users" className="mb-4 flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary">
        <ArrowLeft className="size-4" /> Back to Users
      </Link>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Avatar name={user.full_name} size={44} />
          <div>
            <h1 className="text-2xl font-semibold text-dt-text-primary">{user.full_name}</h1>
            <p className="text-sm text-dt-text-secondary">{user.email}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={user.is_active ? "ACTIVE_CLIENT" : "CANCELLED"} label={user.is_active ? "Active" : "Inactive"} />
          <Button
            size="sm"
            variant={user.is_active ? "danger" : "secondary"}
            onClick={() => statusMutation.mutate(!user.is_active)}
            loading={statusMutation.isPending}
          >
            {user.is_active ? "Deactivate" : "Activate"}
          </Button>
        </div>
      </div>

      {statusError && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dt-danger/30 bg-[color-mix(in_srgb,var(--dt-danger)_6%,white)] px-3 py-2 text-sm text-dt-danger">
          <ShieldAlert className="size-4 shrink-0" /> {statusError}
        </div>
      )}

      <Card className="mb-6 p-5">
        <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Platform Role</p>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={user.platform_role}
            onChange={(e) => roleMutation.mutate(e.target.value)}
            disabled={roleMutation.isPending}
            className="max-w-xs"
          >
            {PLATFORM_ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {PLATFORM_ROLE_LABELS[r]}
              </option>
            ))}
          </Select>
          <p className="text-xs text-dt-text-secondary">
            Granting or revoking SUPER_ADMIN / PLATFORM_ADMIN requires SUPER_ADMIN privileges.
          </p>
        </div>
        <p className="mt-2 text-xs text-dt-text-secondary">
          Identity provider: {user.identity_provider} · Last login: {user.last_login_at ? formatDateTime(user.last_login_at) : "Never"}
        </p>
      </Card>

      <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Application Access</p>
      <div className="grid gap-4">
        {modules.map((m) => {
          const assignment = user.module_assignments.find((a) => a.module_key === m.key);
          const moduleRoles = roles.filter((r) => r.module_key === m.key).map((r) => ({ key: r.key, name: r.name }));
          return (
            <ModuleAssignmentEditor
              key={m.key}
              userId={userId}
              moduleKey={m.key}
              moduleName={m.name}
              moduleStatus={m.status}
              availableRoles={moduleRoles}
              clients={clients}
              current={
                assignment
                  ? {
                      role: assignment.role,
                      enabled: assignment.enabled,
                      all_clients: assignment.client_scope?.all_clients ?? true,
                      client_ids: assignment.client_scope?.client_ids ?? [],
                    }
                  : undefined
              }
              onSaved={() => {
                invalidate();
                queryClient.invalidateQueries({ queryKey: ["admin", "users", userId] });
                queryClient.invalidateQueries({ queryKey: ["admin", "users", userId, "effective-access"] });
              }}
            />
          );
        })}
      </div>

      <p className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Effective Access
      </p>
      <Card className="p-5">
        {effectiveQuery.isLoading && <LoadingState label="Resolving effective access…" />}
        {effectiveQuery.data && (
          <div className="space-y-5">
            <div>
              <p className="text-sm font-medium text-dt-text-primary">Platform Permissions</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {effectiveQuery.data.platform_permissions.length === 0 && (
                  <span className="text-sm text-dt-text-secondary">None</span>
                )}
                {effectiveQuery.data.platform_permissions.map((p) => (
                  <span key={p} className="rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs text-dt-text-secondary">
                    {p}
                  </span>
                ))}
              </div>
            </div>
            {effectiveQuery.data.modules.map((m) => (
              <div key={m.module_key} className="border-t border-dt-border pt-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-dt-text-primary">
                    {m.module_name} — {m.role_name}
                  </p>
                  <StatusBadge status={m.enabled ? "ACTIVE_CLIENT" : "CANCELLED"} label={m.enabled ? "Enabled" : "Disabled"} />
                </div>
                <p className="mt-1 text-sm text-dt-text-secondary">
                  Client Scope:{" "}
                  {m.client_scope.all_clients ? "All Clients" : m.client_scope.client_names.join(", ") || "None"}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {m.permissions.map((p) => (
                    <span key={p} className="rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs text-dt-text-secondary">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
