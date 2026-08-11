"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  listApplications,
  updateApplicationScore,
  updateApplicationStage,
  updateApplicationStatus,
  updateApplicationVisibility,
} from "@/lib/api";
import { APPLICATION_STATUSES, CANONICAL_STAGES } from "@/lib/constants";
import { stageLabel } from "@/lib/utils";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Table, Thead, Th, Tr, Td } from "@/components/ui/Table";

export function ApplicationsView({ initialSearch = "" }: { initialSearch?: string }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState(initialSearch);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["applications", "all", search],
    queryFn: () => listApplications({ search: search || undefined }),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  }

  return (
    <div>
      <PageHeader
        title="Applications"
        description="Manage every candidate application across all clients — stage, status, score and client visibility."
      />

      <div className="relative mb-6 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by designation…"
          className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
        />
      </div>

      {isLoading && <LoadingState label="Loading applications…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && <EmptyState title="No applications found" />}

      {data && data.length > 0 && (
        <Table>
          <Thead>
            <tr>
              <Th>Candidate</Th>
              <Th>Request</Th>
              <Th>Stage</Th>
              <Th>Status</Th>
              <Th>Score</Th>
              <Th>Client Visible</Th>
            </tr>
          </Thead>
          <tbody>
            {data.map((app) => (
              <Tr key={app.id}>
                <Td className="font-medium">
                  <Link href={`/talent-flow/candidates/${app.candidate_id}`} className="hover:text-dt-burnt-orange">
                    {app.candidate_name}
                  </Link>
                </Td>
                <Td>
                  <Link href={`/talent-flow/requests/${app.talent_request_id}`} className="hover:text-dt-burnt-orange">
                    {app.designation}
                  </Link>
                  <p className="text-xs text-dt-text-secondary">{app.client_name}</p>
                </Td>
                <Td>
                  <Select
                    value={app.current_stage}
                    onChange={async (e) => {
                      await updateApplicationStage(app.id, e.target.value);
                      invalidate();
                    }}
                    className="w-44 py-1.5 text-xs"
                  >
                    {CANONICAL_STAGES.map((s) => (
                      <option key={s} value={s}>
                        {stageLabel(s)}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <Select
                    value={app.status}
                    onChange={async (e) => {
                      await updateApplicationStatus(app.id, e.target.value);
                      invalidate();
                    }}
                    className="w-36 py-1.5 text-xs"
                  >
                    {APPLICATION_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {stageLabel(s)}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    step={0.1}
                    defaultValue={app.score ?? ""}
                    onBlur={async (e) => {
                      const value = e.target.value === "" ? null : Number(e.target.value);
                      if (value !== null) {
                        await updateApplicationScore(app.id, value);
                        invalidate();
                      }
                    }}
                    className="w-16 rounded-lg border border-dt-border px-2 py-1 text-xs focus:border-dt-orange focus:outline-none"
                  />
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
