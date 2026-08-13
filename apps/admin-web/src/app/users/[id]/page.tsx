"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ShieldAlert } from "lucide-react";
import Link from "next/link";
import {
  ApiError,
  addGroupMember,
  getAdminGroup,
  getAdminUser,
  getEffectiveAccess,
  listAdminAudit,
  listAdminClients,
  listAdminGroups,
  listAdminModules,
  listAdminRoles,
  removeGroupMember,
  updatePlatformRole,
  updateUserStatus,
  upsertModuleAssignment,
} from "@/lib/api";
import { PLATFORM_ROLE_LABELS } from "@dijione/contracts";
import {
  Avatar,
  Button,
  Card,
  cn,
  ErrorState,
  formatDateTime,
  LoadingState,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";

const PLATFORM_ROLE_OPTIONS = ["PLATFORM_USER", "PLATFORM_ADMIN", "SUPER_ADMIN"];

const TABS = ["Overview", "Applications", "Groups", "Client Access", "Effective Access", "Audit History"] as const;
type Tab = (typeof TABS)[number];

function useUserQueries(userId: number) {
  const userQuery = useQuery({ queryKey: ["admin", "users", userId], queryFn: () => getAdminUser(userId) });
  const rolesQuery = useQuery({ queryKey: ["admin", "roles"], queryFn: listAdminRoles });
  const modulesQuery = useQuery({ queryKey: ["admin", "modules"], queryFn: listAdminModules });
  const clientsQuery = useQuery({ queryKey: ["admin", "clients"], queryFn: listAdminClients });
  const effectiveQuery = useQuery({
    queryKey: ["admin", "users", userId, "effective-access"],
    queryFn: () => getEffectiveAccess(userId),
  });
  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listAdminGroups });
  // AdminUserOut doesn't carry group membership directly — derive it by
  // cross-referencing each group's member list (dataset is small; see
  // CLAUDE.md §8 scope discipline — avoid a new backend endpoint for this).
  const userGroupsQuery = useQuery({
    queryKey: ["admin", "users", userId, "groups"],
    queryFn: async () => {
      const groups = await listAdminGroups();
      const details = await Promise.all(groups.map((g) => getAdminGroup(g.id)));
      return details.filter((d) => d.members.some((m) => m.user_id === userId));
    },
  });
  const auditQuery = useQuery({
    queryKey: ["admin", "audit", "User", userId],
    queryFn: () => listAdminAudit({ entity_type: "User", entity_id: userId }),
  });
  return { userQuery, rolesQuery, modulesQuery, clientsQuery, effectiveQuery, groupsQuery, userGroupsQuery, auditQuery };
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

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div className="mb-6 flex flex-wrap gap-1 border-b border-dt-border">
      {TABS.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={cn(
            "-mb-px rounded-t-lg border-b-2 px-3.5 py-2 text-sm font-medium transition",
            active === t
              ? "border-dt-orange text-dt-burnt-orange"
              : "border-transparent text-dt-text-secondary hover:text-dt-text-primary"
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

export default function AdminUserDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const userId = Number(params.id);
  const queryClient = useQueryClient();
  const {
    userQuery,
    rolesQuery,
    modulesQuery,
    clientsQuery,
    effectiveQuery,
    groupsQuery,
    userGroupsQuery,
    auditQuery,
  } = useUserQueries(userId);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [addGroupId, setAddGroupId] = useState<number | "">("");

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

  const invalidateGroups = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "users", userId, "groups"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "groups"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "users", userId, "effective-access"] });
  };

  const addToGroupMutation = useMutation({
    mutationFn: (groupId: number) => addGroupMember(groupId, userId),
    onSuccess: () => {
      setAddGroupId("");
      invalidateGroups();
    },
    onError: (e: unknown) => setStatusError(e instanceof ApiError ? e.message : "Could not add user to group."),
  });

  const removeFromGroupMutation = useMutation({
    mutationFn: (groupId: number) => removeGroupMember(groupId, userId),
    onSuccess: invalidateGroups,
    onError: (e: unknown) => setStatusError(e instanceof ApiError ? e.message : "Could not remove user from group."),
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
  const userGroups = userGroupsQuery.data ?? [];
  const userGroupIds = new Set(userGroups.map((g) => g.id));
  const availableGroupsToAdd = (groupsQuery.data ?? []).filter((g) => !userGroupIds.has(g.id));

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

      <TabBar active={tab} onChange={setTab} />

      {tab === "Overview" && (
        <Card className="p-5">
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
      )}

      {tab === "Applications" && (
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
      )}

      {tab === "Groups" && (
        <Card className="p-5">
          <div className="mb-4 flex flex-wrap items-end gap-2">
            <Select
              value={addGroupId}
              onChange={(e) => setAddGroupId(e.target.value ? Number(e.target.value) : "")}
              className="max-w-xs"
            >
              <option value="">Add to group…</option>
              {availableGroupsToAdd.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.display_name}
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              onClick={() => addGroupId && addToGroupMutation.mutate(addGroupId as number)}
              disabled={!addGroupId}
              loading={addToGroupMutation.isPending}
            >
              Add
            </Button>
          </div>

          {userGroupsQuery.isLoading && <LoadingState label="Loading group memberships…" />}
          {!userGroupsQuery.isLoading && userGroups.length === 0 && (
            <p className="text-sm text-dt-text-secondary">This user is not a member of any access group.</p>
          )}
          <div className="flex flex-col divide-y divide-dt-border">
            {userGroups.map((g) => (
              <div key={g.id} className="flex items-center justify-between py-2.5">
                <div>
                  <Link href={`/groups/${g.id}`} className="text-sm font-medium text-dt-burnt-orange">
                    {g.display_name}
                  </Link>
                  <p className="text-xs text-dt-text-secondary">{g.group_type} · {g.module_assignments.length} module{g.module_assignments.length === 1 ? "" : "s"}</p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeFromGroupMutation.mutate(g.id)}
                  loading={removeFromGroupMutation.isPending}
                >
                  Remove
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === "Client Access" && (
        <Card className="p-5">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Client Scope by Application</p>
          <div className="flex flex-col divide-y divide-dt-border">
            {user.module_assignments.length === 0 && (
              <p className="text-sm text-dt-text-secondary">No module assignments yet.</p>
            )}
            {user.module_assignments.map((a) => (
              <div key={a.module_key} className="py-2.5">
                <p className="text-sm font-medium text-dt-text-primary">{a.module_name}</p>
                <p className="text-sm text-dt-text-secondary">
                  {a.client_scope?.all_clients ? "All Clients" : a.client_scope?.client_names.join(", ") || "None"}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === "Effective Access" && (
        <Card className="p-5">
          <a
            href="/guide#effective-access"
            className="mb-4 inline-block text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
          >
            How is effective access calculated?
          </a>
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
                    {/*
                      `sources` is mandatory in the current admin-api/platform-api contract
                      (AccessSourceOut[], always populated by AdminService.effective_access).
                      Guard with `?? []` anyway: a rolling deploy can put a newer admin-web
                      build in front of an older/stale platform-api process that predates this
                      field, and the UI must degrade to "no source info" rather than crash.
                    */}
                    {(m.sources ?? []).length === 0 && (
                      <span className="text-xs text-dt-text-secondary">Access source unavailable</span>
                    )}
                    {(m.sources ?? []).map((s, idx) => (
                      <StatusBadge
                        key={idx}
                        status={s.type}
                        label={s.type === "DIRECT" ? "Direct" : `Inherited from ${s.group_name}`}
                      />
                    ))}
                  </div>
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
      )}

      {tab === "Audit History" && (
        <>
          {auditQuery.isLoading && <LoadingState label="Loading audit history…" />}
          {auditQuery.isError && <ErrorState message="Could not load audit history." onRetry={() => auditQuery.refetch()} />}
          {auditQuery.data && auditQuery.data.length === 0 && (
            <Card className="p-5 text-sm text-dt-text-secondary">No audit events for this user yet.</Card>
          )}
          {auditQuery.data && auditQuery.data.length > 0 && (
            <Table>
              <Thead>
                <tr>
                  <Th>When</Th>
                  <Th>Actor</Th>
                  <Th>Action</Th>
                  <Th>Details</Th>
                </tr>
              </Thead>
              <tbody>
                {auditQuery.data.map((e) => (
                  <Tr key={e.id}>
                    <Td className="whitespace-nowrap text-sm text-dt-text-secondary">{formatDateTime(e.created_at)}</Td>
                    <Td className="text-sm">{e.actor_name ?? "System"}</Td>
                    <Td>
                      <code className="rounded bg-dt-surface-warm px-1.5 py-0.5 text-xs">{e.action}</code>
                    </Td>
                    <Td className="max-w-xs truncate text-xs text-dt-text-secondary" title={e.new_state}>
                      {e.new_state || e.previous_state || "—"}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}
