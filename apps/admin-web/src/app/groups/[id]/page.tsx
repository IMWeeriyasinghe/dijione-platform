"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Plus, Search, ShieldAlert, Trash2, UserPlus } from "lucide-react";
import Link from "next/link";
import {
  ApiError,
  getAdminGroup,
  listAdminClients,
  listAdminModules,
  listAdminRoles,
  listAdminUsers,
  addGroupMember,
  removeGroupMember,
  removeGroupModuleAssignment,
  setGroupStatus,
  updateAdminGroup,
  upsertGroupModuleAssignment,
} from "@/lib/api";
import {
  Avatar,
  Button,
  Card,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Select,
  StatusBadge,
  Textarea,
} from "@dijione/design-system";

function useGroupQueries(groupId: number) {
  const groupQuery = useQuery({ queryKey: ["admin", "groups", groupId], queryFn: () => getAdminGroup(groupId) });
  const rolesQuery = useQuery({ queryKey: ["admin", "roles"], queryFn: listAdminRoles });
  const modulesQuery = useQuery({ queryKey: ["admin", "modules"], queryFn: listAdminModules });
  const clientsQuery = useQuery({ queryKey: ["admin", "clients"], queryFn: listAdminClients });
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listAdminUsers });
  return { groupQuery, rolesQuery, modulesQuery, clientsQuery, usersQuery };
}

function GroupModuleAssignmentEditor({
  groupId,
  moduleKey,
  moduleName,
  moduleStatus,
  availableRoles,
  clients,
  current,
  onSaved,
}: {
  groupId: number;
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

  const saveMutation = useMutation({
    mutationFn: () =>
      upsertGroupModuleAssignment(groupId, moduleKey, {
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

  const removeMutation = useMutation({
    mutationFn: () => removeGroupModuleAssignment(groupId, moduleKey),
    onSuccess: () => {
      setError(null);
      onSaved();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not remove this module assignment."),
  });

  if (availableRoles.length === 0) {
    return (
      <Card className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-dt-text-primary">{moduleName}</p>
            <p className="mt-1 text-sm text-dt-text-secondary">No functional roles are defined for this module yet.</p>
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
            <input type="checkbox" checked={allClients} onChange={(e) => setAllClients(e.target.checked)} disabled={!enabled} />
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
                  setClientIds((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((id) => id !== c.id)))
                }
              />
              {c.name}
            </label>
          ))}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-dt-danger">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
          Save {moduleName} Access
        </Button>
        {current && (
          <Button size="sm" variant="secondary" onClick={() => removeMutation.mutate()} loading={removeMutation.isPending}>
            Remove Assignment
          </Button>
        )}
      </div>
    </Card>
  );
}

type CandidateUser = { id: number; full_name: string; email: string };

function MemberSelector({
  candidates,
  onAdd,
  isAdding,
}: {
  candidates: CandidateUser[];
  onAdd: (userId: number) => void;
  isAdding: boolean;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<CandidateUser | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const results = query.trim()
    ? candidates.filter(
        (u) =>
          u.full_name.toLowerCase().includes(query.toLowerCase()) ||
          u.email.toLowerCase().includes(query.toLowerCase())
      )
    : candidates;

  return (
    <div className="mb-4 flex items-end gap-2">
      <div className="relative flex-1">
        <label htmlFor="member-search" className="mb-1.5 block text-sm font-medium text-dt-text-primary">
          Add member
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
          <Input
            id="member-search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelected(null);
              setIsOpen(true);
            }}
            onFocus={() => setIsOpen(true)}
            onBlur={() => setTimeout(() => setIsOpen(false), 120)}
            placeholder="Search or select user by name/email…"
            className="h-10 pl-9"
          />
        </div>
        {isOpen && (
          <div className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-dt-border bg-dt-surface shadow-lg">
            {results.length === 0 ? (
              <p className="px-3 py-2 text-sm text-dt-text-secondary">No matching users.</p>
            ) : (
              results.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    setSelected(u);
                    setQuery(`${u.full_name} (${u.email})`);
                    setIsOpen(false);
                  }}
                  className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-dt-surface-warm"
                >
                  <span className="font-medium text-dt-text-primary">{u.full_name}</span>
                  <span className="text-xs text-dt-text-secondary">{u.email}</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
      <Button
        size="sm"
        className="h-10"
        onClick={() => {
          if (!selected) return;
          onAdd(selected.id);
          setSelected(null);
          setQuery("");
        }}
        disabled={!selected}
        loading={isAdding}
      >
        <Plus className="size-4" /> Add
      </Button>
    </div>
  );
}

export default function AdminGroupDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const groupId = Number(params.id);
  const queryClient = useQueryClient();
  const { groupQuery, rolesQuery, modulesQuery, clientsQuery, usersQuery } = useGroupQueries(groupId);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "groups"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "groups", groupId] });
  };

  const statusMutation = useMutation({
    mutationFn: (status: string) => setGroupStatus(groupId, status),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not update group status."),
  });

  const updateMutation = useMutation({
    mutationFn: () => updateAdminGroup(groupId, { display_name: displayName, description }),
    onSuccess: () => {
      setError(null);
      setEditing(false);
      invalidate();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not update this group."),
  });

  const addMemberMutation = useMutation({
    mutationFn: (userId: number) => addGroupMember(groupId, userId),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not add this member."),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (userId: number) => removeGroupMember(groupId, userId),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not remove this member."),
  });

  if (groupQuery.isLoading || rolesQuery.isLoading || modulesQuery.isLoading || clientsQuery.isLoading || usersQuery.isLoading) {
    return <LoadingState label="Loading group…" />;
  }
  if (groupQuery.isError || !groupQuery.data) {
    return <ErrorState message="Could not load this group." onRetry={() => router.refresh()} />;
  }

  const group = groupQuery.data;
  const roles = rolesQuery.data ?? [];
  const modules = modulesQuery.data ?? [];
  const clients = clientsQuery.data ?? [];
  const allUsers = usersQuery.data ?? [];
  const memberIds = new Set(group.members.map((m) => m.user_id));
  const isSystemGroup = group.group_type === "SYSTEM";

  const candidateUsers = allUsers.filter((u) => !memberIds.has(u.id));
  const userStatusById = new Map(allUsers.map((u) => [u.id, u.is_active]));

  return (
    <div>
      <Link href="/groups" className="mb-4 flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary">
        <ArrowLeft className="size-4" /> Back to Groups
      </Link>

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-dt-text-primary">{group.display_name}</h1>
          <p className="text-sm text-dt-text-secondary">{group.key} · {group.group_type}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={group.status === "ACTIVE" ? "ACTIVE_CLIENT" : "INACTIVE"} label={group.status === "ACTIVE" ? "Active" : "Inactive"} />
          <Button
            size="sm"
            variant={group.status === "ACTIVE" ? "danger" : "secondary"}
            onClick={() => statusMutation.mutate(group.status === "ACTIVE" ? "INACTIVE" : "ACTIVE")}
            loading={statusMutation.isPending}
            disabled={isSystemGroup}
            title={isSystemGroup ? "System groups cannot be deactivated" : undefined}
          >
            {group.status === "ACTIVE" ? "Deactivate" : "Activate"}
          </Button>
        </div>
      </div>

      {isSystemGroup && (
        <p className="mb-4 text-xs text-dt-text-secondary">
          This is a system group — its status is protected and cannot be disabled from the admin UI.
        </p>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dt-danger/30 bg-[color-mix(in_srgb,var(--dt-danger)_6%,white)] px-3 py-2 text-sm text-dt-danger">
          <ShieldAlert className="size-4 shrink-0" /> {error}
        </div>
      )}

      <Card className="mb-6 p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Details</p>
          {!editing && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setDisplayName(group.display_name);
                setDescription(group.description ?? "");
                setEditing(true);
              }}
            >
              Edit
            </Button>
          )}
        </div>
        {editing ? (
          <div className="flex flex-col gap-3">
            <FormField label="Display Name" htmlFor="edit-name">
              <Input id="edit-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </FormField>
            <FormField label="Description" htmlFor="edit-desc">
              <Textarea id="edit-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
            </FormField>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => updateMutation.mutate()} loading={updateMutation.isPending}>
                Save
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-dt-text-secondary">{group.description || "No description."}</p>
        )}
      </Card>

      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Members</p>
        <a href="/guide#direct-vs-inherited" className="text-xs font-medium text-dt-burnt-orange underline underline-offset-2">
          Learn about inherited access
        </a>
      </div>
      <Card className="mb-6 p-5">
        <MemberSelector
          candidates={candidateUsers}
          onAdd={(userId) => addMemberMutation.mutate(userId)}
          isAdding={addMemberMutation.isPending}
        />

        {group.members.length === 0 ? (
          <div className="flex flex-col items-center gap-1.5 rounded-lg border border-dashed border-dt-border py-8 text-center">
            <UserPlus className="size-5 text-dt-text-secondary" />
            <p className="text-sm text-dt-text-secondary">No members yet. Add someone using the field above.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-dt-border text-left text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">
                  <th className="py-2 pr-3 font-semibold">Name</th>
                  <th className="py-2 pr-3 font-semibold">Email</th>
                  <th className="py-2 pr-3 font-semibold">Status</th>
                  <th className="py-2 pl-3 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dt-border">
                {group.members.map((m) => (
                  <tr key={m.user_id}>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center gap-3">
                        <Avatar name={m.full_name} size={28} />
                        <span className="font-medium text-dt-text-primary">{m.full_name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-dt-text-secondary">{m.email}</td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={userStatusById.get(m.user_id) === false ? "INACTIVE" : "ACTIVE_CLIENT"} label={userStatusById.get(m.user_id) === false ? "Inactive" : "Active"} />
                    </td>
                    <td className="py-2.5 pl-3 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeMemberMutation.mutate(m.user_id)}
                        loading={removeMemberMutation.isPending}
                      >
                        <Trash2 className="size-4 text-dt-danger" /> Remove
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Application Access</p>
      <div className="grid gap-4">
        {modules.map((m) => {
          const assignment = group.module_assignments.find((a) => a.module_key === m.key);
          const moduleRoles = roles.filter((r) => r.module_key === m.key).map((r) => ({ key: r.key, name: r.name }));
          return (
            <GroupModuleAssignmentEditor
              key={m.key}
              groupId={groupId}
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
              onSaved={invalidate}
            />
          );
        })}
      </div>
    </div>
  );
}
