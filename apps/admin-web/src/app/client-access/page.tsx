"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { ApiError, listAdminClients, listAdminUsers, upsertModuleAssignment } from "@/lib/api";
import { MODULE_TALENT_FLOW } from "@dijione/contracts";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { Button } from "@dijione/design-system";
import { LoadingState, ErrorState, EmptyState } from "@dijione/design-system";

function ClientAccessRow({
  userId,
  fullName,
  role,
  roleLabel,
  clients,
  initialAllClients,
  initialClientIds,
}: {
  userId: number;
  fullName: string;
  role: string;
  roleLabel: string;
  clients: { id: number; name: string }[];
  initialAllClients: boolean;
  initialClientIds: number[];
}) {
  const [allClients, setAllClients] = useState(initialAllClients);
  const [clientIds, setClientIds] = useState<number[]>(initialClientIds);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      upsertModuleAssignment(userId, MODULE_TALENT_FLOW, {
        role,
        enabled: true,
        client_scope: { all_clients: allClients, client_ids: allClients ? [] : clientIds },
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Could not save client access."),
  });

  return (
    <div className="flex flex-col gap-3 border-b border-dt-border py-4 last:border-0">
      <div className="flex items-center justify-between">
        <div>
          <Link href={`/users/${userId}`} className="font-medium text-dt-text-primary hover:underline">
            {fullName}
          </Link>
          <p className="text-xs text-dt-text-secondary">{roleLabel}</p>
        </div>
        <Button size="sm" onClick={() => mutation.mutate()} loading={mutation.isPending}>
          Save
        </Button>
      </div>
      <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
        <input type="checkbox" checked={allClients} onChange={(e) => setAllClients(e.target.checked)} />
        All Clients
      </label>
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
    </div>
  );
}

export default function AdminClientAccessPage() {
  const usersQuery = useQuery({ queryKey: ["admin", "users"], queryFn: listAdminUsers });
  const clientsQuery = useQuery({ queryKey: ["admin", "clients"], queryFn: listAdminClients });

  const staffAssignments = (usersQuery.data ?? [])
    .flatMap((u) =>
      u.module_assignments
        .filter((a) => a.module_key === MODULE_TALENT_FLOW && a.role !== "TALENT_CLIENT")
        .map((a) => ({ user: u, assignment: a }))
    )
    .filter(({ assignment }) => assignment.enabled);

  return (
    <div>
      <PageHeader
        title="Client Access"
        description="Assign DijiTalentFlow client/portfolio scope to Talent Acquisition and Customer Success staff. External client users (TALENT_CLIENT) are always scoped to their own organization and are managed from the user detail page instead."
      />
      {(usersQuery.isLoading || clientsQuery.isLoading) && <LoadingState label="Loading client access…" />}
      {(usersQuery.isError || clientsQuery.isError) && (
        <ErrorState message="Could not load client access data." onRetry={() => usersQuery.refetch()} />
      )}
      {usersQuery.data && clientsQuery.data && staffAssignments.length === 0 && (
        <EmptyState title="No staff assignments found" description="Assign a TA/Customer Success role to a user first." />
      )}
      {usersQuery.data && clientsQuery.data && staffAssignments.length > 0 && (
        <Card className="p-5">
          {staffAssignments.map(({ user, assignment }) => (
            <ClientAccessRow
              key={user.id}
              userId={user.id}
              fullName={user.full_name}
              role={assignment.role}
              roleLabel={assignment.role_name}
              clients={clientsQuery.data!}
              initialAllClients={assignment.client_scope?.all_clients ?? true}
              initialClientIds={assignment.client_scope?.client_ids ?? []}
            />
          ))}
        </Card>
      )}
    </div>
  );
}
