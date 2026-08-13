"use client";

import { useQuery } from "@tanstack/react-query";
import { listAdminPermissions } from "@/lib/api";
import type { AdminPermissionOut } from "@dijione/contracts";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { LoadingState, ErrorState } from "@dijione/design-system";

function groupByCategory(permissions: AdminPermissionOut[]) {
  const groups = new Map<string, AdminPermissionOut[]>();
  for (const p of permissions) {
    const key = `${p.module_key ?? "Platform"} · ${p.category}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }
  return groups;
}

export default function AdminPermissionsPage() {
  const query = useQuery({ queryKey: ["admin", "permissions"], queryFn: listAdminPermissions });
  const groups = query.data ? groupByCategory(query.data) : null;

  return (
    <div>
      <PageHeader
        title="Permissions"
        description="Every atomic action a role can bundle. Permissions are read-only in this MVP — manage them by adjusting which roles include which permissions."
      />
      {query.isLoading && <LoadingState label="Loading permissions…" />}
      {query.isError && <ErrorState message="Could not load permissions." onRetry={() => query.refetch()} />}
      {groups && (
        <div className="space-y-6">
          {Array.from(groups.entries()).map(([group, permissions]) => (
            <div key={group}>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">{group}</h3>
              <Card className="divide-y divide-dt-border p-0">
                {permissions.map((p) => (
                  <div key={p.id} className="flex flex-col gap-0.5 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-dt-text-primary">{p.name}</p>
                      <code className="shrink-0 rounded bg-dt-surface-warm px-1.5 py-0.5 text-xs text-dt-text-secondary">
                        {p.key}
                      </code>
                    </div>
                    {p.description && <p className="text-sm text-dt-text-secondary">{p.description}</p>}
                  </div>
                ))}
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
