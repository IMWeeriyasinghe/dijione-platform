"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { listApplications, updateApplicationVisibility } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { Table, Thead, Th, Tr, Td } from "@dijione/design-system";

export function ApplicationsView({
  initialSearch = "",
  initialStatus = "",
}: {
  initialSearch?: string;
  initialStatus?: string;
}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState(initialSearch);
  // The API has no status_filter for applications — this is a frontend-only
  // filter applied after fetch, used by the Operations Dashboard's "Offers
  // in Progress" click-through (?status=OFFER).
  const [statusFilter, setStatusFilter] = useState(initialStatus);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["applications", "all", search],
    queryFn: () => listApplications({ search: search || undefined }),
  });

  const rows = statusFilter ? data?.filter((a) => a.status === statusFilter) : data;

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  }

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Monitor every candidate application across all clients — stage and status are synced from Lever; client visibility is the one thing you curate here."
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by designation…"
            className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          />
        </div>
        {statusFilter && (
          <button
            type="button"
            onClick={() => setStatusFilter("")}
            className="flex items-center gap-1.5 rounded-full border border-dt-orange/30 bg-dt-surface-warm px-3 py-1 text-xs font-medium text-dt-burnt-orange"
          >
            Status: {statusFilter}
            <span aria-hidden>×</span>
          </button>
        )}
      </div>

      {isLoading && <LoadingState label="Loading applications…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {rows && rows.length === 0 && <EmptyState title="No applications found" />}

      {rows && rows.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>Candidate</Th>
              <Th>Request</Th>
              <Th>Stage</Th>
              <Th>Status</Th>
              <Th>Client Visible</Th>
            </tr>
          </Thead>
          <tbody>
            {rows.map((app) => (
              <Tr key={app.id}>
                <Td className="font-medium">
                  <Link href={`/candidates/${app.candidate_id}`} className="hover:text-dt-burnt-orange">
                    {app.candidate_name}
                  </Link>
                </Td>
                <Td>
                  <Link href={`/requests/${app.talent_request_id}`} className="hover:text-dt-burnt-orange">
                    {app.designation}
                  </Link>
                  <p className="text-xs text-dt-text-secondary">{app.client_name}</p>
                </Td>
                <Td>
                  <StatusBadge status={app.current_stage} />
                  <p className="mt-1 text-[11px] text-dt-text-secondary">Synced from Lever</p>
                </Td>
                <Td>
                  <StatusBadge status={app.status} />
                  <p className="mt-1 text-[11px] text-dt-text-secondary">Synced from Lever</p>
                </Td>
                <Td>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      defaultChecked={app.is_client_visible}
                      onChange={async (e) => {
                        await updateApplicationVisibility(app.id, e.target.checked);
                        invalidate();
                      }}
                      className="size-4 accent-[var(--dt-orange)]"
                    />
                    {app.is_client_visible ? <StatusBadge status="APPROVED" label="Visible" /> : "Hidden"}
                  </label>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
