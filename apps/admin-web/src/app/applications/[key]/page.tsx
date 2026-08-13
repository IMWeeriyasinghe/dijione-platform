"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import Link from "next/link";
import {
  ApiError,
  getApplicationDetail,
  listAdminClients,
  listAdminGroups,
  listAdminRoles,
  listAdminUsers,
  upsertGroupModuleAssignment,
  upsertModuleAssignment,
} from "@/lib/api";
import {
  Button,
  Card,
  ErrorState,
  FormField,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";

function useApplicationQueries(moduleKey: string) {
  const detailQuery = useQuery({
    queryKey: ["admin", "applications", moduleKey],
    queryFn: () => getApplicationDetail(moduleKey),
  });
  const rolesQuery = useQuery({ queryKey: ["admin", "roles"], queryFn: listAdminRoles });
  const clientsQuery = useQuery({ queryKey: ["admin", "clients"], queryFn: listAdminClients });
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listAdminUsers });
  const groupsQuery = useQuery({ queryKey: ["admin", "groups"], queryFn: listAdminGroups });
  return { detailQuery, rolesQuery, clientsQuery, usersQuery, groupsQuery };
}

function AssignModal({
  open,
  onClose,
  onAssigned,
  moduleKey,
  moduleRoles,
  clients,
  principals,
  principalLabel,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onAssigned: () => void;
  moduleKey: string;
  moduleRoles: { key: string; name: string }[];
  clients: { id: number; name: string }[];
  principals: { id: number; label: string }[];
  principalLabel: string;
  onSubmit: (principalId: number, role: string, allClients: boolean, clientIds: number[]) => Promise<unknown>;
}) {
  const [principalId, setPrincipalId] = useState<number | "">("");
  const [role, setRole] = useState(moduleRoles[0]?.key ?? "");
  const [allClients, setAllClients] = useState(true);
  const [clientIds, setClientIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      if (!principalId) throw new Error("select-required");
      return onSubmit(principalId as number, role, allClients, clientIds);
    },
    onSuccess: () => {
      setError(null);
      setPrincipalId("");
      onAssigned();
      onClose();
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not save this assignment."),
  });

  return (
    <Modal open={open} onClose={onClose} title={`Assign ${principalLabel}`}>
      <div className="flex flex-col gap-4">
        <FormField label={principalLabel} htmlFor={`assign-${moduleKey}-principal`} required>
          <Select
            id={`assign-${moduleKey}-principal`}
            value={principalId}
            onChange={(e) => setPrincipalId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Select…</option>
            {principals.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Role" htmlFor={`assign-${moduleKey}-role`} required>
          <Select id={`assign-${moduleKey}-role`} value={role} onChange={(e) => setRole(e.target.value)}>
            {moduleRoles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Client Scope" htmlFor={`assign-${moduleKey}-scope`}>
          <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
            <input type="checkbox" checked={allClients} onChange={(e) => setAllClients(e.target.checked)} />
            All Clients
          </label>
        </FormField>
        {!allClients && (
          <div className="flex flex-wrap gap-3 rounded-lg border border-dt-border bg-dt-surface-warm p-3">
            {clients.map((c) => (
              <label key={c.id} className="flex items-center gap-1.5 text-sm text-dt-text-primary">
                <input
                  type="checkbox"
                  checked={clientIds.includes(c.id)}
                  onChange={(e) =>
                    setClientIds((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((id) => id !== c.id)))
                  }
                />
                {c.name}
              </label>
            ))}
          </div>
        )}
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => mutation.mutate()} loading={mutation.isPending} disabled={!principalId || !role}>
            Assign
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function AdminApplicationDetailPage() {
  const params = useParams<{ key: string }>();
  const router = useRouter();
  const moduleKey = params.key;
  const queryClient = useQueryClient();
  const { detailQuery, rolesQuery, clientsQuery, usersQuery, groupsQuery } = useApplicationQueries(moduleKey);
  const [assignUserOpen, setAssignUserOpen] = useState(false);
  const [assignGroupOpen, setAssignGroupOpen] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "applications", moduleKey] });
    queryClient.invalidateQueries({ queryKey: ["admin", "modules"] });
  };

  if (detailQuery.isLoading || rolesQuery.isLoading || clientsQuery.isLoading || usersQuery.isLoading || groupsQuery.isLoading) {
    return <LoadingState label="Loading application…" />;
  }
  if (detailQuery.isError || !detailQuery.data) {
    return <ErrorState message="Could not load this application." onRetry={() => router.refresh()} />;
  }

  const app = detailQuery.data;
  const clients = clientsQuery.data ?? [];
  const users = usersQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const moduleRoles = (rolesQuery.data ?? [])
    .filter((r) => r.module_key === moduleKey)
    .map((r) => ({ key: r.key, name: r.name }));

  const assignedUserIds = new Set(app.assigned_users.map((u) => u.user_id));
  const assignedGroupIds = new Set(app.assigned_groups.map((g) => g.group_id));

  return (
    <div>
      <Link href="/applications" className="mb-4 flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary">
        <ArrowLeft className="size-4" /> Back to Applications
      </Link>

      <PageHeader
        title={app.module_name}
        description={app.description}
        action={<StatusBadge status={app.status} />}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Directly Assigned Users</p>
          <p className="mt-1 text-2xl font-semibold text-dt-text-primary">{app.direct_user_count}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Groups With Access</p>
          <p className="mt-1 text-2xl font-semibold text-dt-text-primary">{app.group_count}</p>
        </Card>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Assigned Users</p>
        <Button size="sm" onClick={() => setAssignUserOpen(true)} disabled={moduleRoles.length === 0}>
          <Plus className="size-4" /> Assign User
        </Button>
      </div>
      {app.assigned_users.length === 0 ? (
        <Card className="mb-6 p-5 text-sm text-dt-text-secondary">No users are directly assigned to this application.</Card>
      ) : (
        <Table>
          <Thead>
            <tr>
              <Th>User</Th>
              <Th>Role</Th>
              <Th>Client Scope</Th>
              <Th>Status</Th>
            </tr>
          </Thead>
          <tbody>
            {app.assigned_users.map((u) => (
              <Tr key={u.user_id}>
                <Td>
                  <p className="font-medium text-dt-text-primary">{u.full_name}</p>
                  <p className="text-xs text-dt-text-secondary">{u.email}</p>
                </Td>
                <Td className="text-sm text-dt-text-secondary">{u.role_name}</Td>
                <Td className="text-sm text-dt-text-secondary">
                  {u.client_scope.all_clients ? "All Clients" : u.client_scope.client_names.join(", ") || "None"}
                </Td>
                <Td>
                  <StatusBadge status={u.enabled ? "ACTIVE_CLIENT" : "INACTIVE"} label={u.enabled ? "Enabled" : "Disabled"} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      <div className="mb-3 mt-8 flex items-center justify-between">
        <p className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">Assigned Groups</p>
        <Button size="sm" onClick={() => setAssignGroupOpen(true)} disabled={moduleRoles.length === 0}>
          <Plus className="size-4" /> Assign Group
        </Button>
      </div>
      {app.assigned_groups.length === 0 ? (
        <Card className="p-5 text-sm text-dt-text-secondary">No groups have access to this application.</Card>
      ) : (
        <Table>
          <Thead>
            <tr>
              <Th>Group</Th>
              <Th>Role</Th>
              <Th>Client Scope</Th>
              <Th>Status</Th>
            </tr>
          </Thead>
          <tbody>
            {app.assigned_groups.map((g) => (
              <Tr key={g.group_id}>
                <Td>
                  <Link href={`/groups/${g.group_id}`} className="font-medium text-dt-burnt-orange">
                    {g.group_name}
                  </Link>
                  <p className="text-xs text-dt-text-secondary">{g.group_key}</p>
                </Td>
                <Td className="text-sm text-dt-text-secondary">{g.role_name}</Td>
                <Td className="text-sm text-dt-text-secondary">
                  {g.client_scope.all_clients ? "All Clients" : g.client_scope.client_names.join(", ") || "None"}
                </Td>
                <Td>
                  <StatusBadge status={g.enabled ? "ACTIVE_CLIENT" : "INACTIVE"} label={g.enabled ? "Enabled" : "Disabled"} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      <AssignModal
        open={assignUserOpen}
        onClose={() => setAssignUserOpen(false)}
        onAssigned={invalidate}
        moduleKey={moduleKey}
        moduleRoles={moduleRoles}
        clients={clients}
        principals={users
          .filter((u) => !assignedUserIds.has(u.id))
          .map((u) => ({ id: u.id, label: `${u.full_name} (${u.email})` }))}
        principalLabel="User"
        onSubmit={(userId, role, allClients, clientIds) =>
          upsertModuleAssignment(userId, moduleKey, {
            role,
            enabled: true,
            client_scope: { all_clients: allClients, client_ids: allClients ? [] : clientIds },
          })
        }
      />
      <AssignModal
        open={assignGroupOpen}
        onClose={() => setAssignGroupOpen(false)}
        onAssigned={invalidate}
        moduleKey={moduleKey}
        moduleRoles={moduleRoles}
        clients={clients}
        principals={groups
          .filter((g) => !assignedGroupIds.has(g.id))
          .map((g) => ({ id: g.id, label: g.display_name }))}
        principalLabel="Group"
        onSubmit={(groupId, role, allClients, clientIds) =>
          upsertGroupModuleAssignment(groupId, moduleKey, {
            role,
            enabled: true,
            client_scope: { all_clients: allClients, client_ids: allClients ? [] : clientIds },
          })
        }
      />
    </div>
  );
}
