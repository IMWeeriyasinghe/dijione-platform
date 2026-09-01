"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { listTalentRequests } from "@/lib/api";
import { useTalentScope } from "@dijione/auth-client";
import { PageHeader } from "@dijione/design-system";
import { Select } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { CANONICAL_STAGES, LIFECYCLE_STATUSES } from "@dijione/contracts";
import { stageLabel } from "@dijione/design-system";

export default function RequestsPage() {
  const scope = useTalentScope();
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["talent-requests", search, stage, status],
    queryFn: () =>
      listTalentRequests({
        search: search || undefined,
        stage: stage || undefined,
        status_filter: status || undefined,
      }),
  });

  if (!scope) return null;

  return (
    <div>
      <PageHeader
        title={scope.isStaff ? "All Requests" : "My Requests"}
        description={
          scope.isStaff
            ? "Cross-client queue of every talent request in DijiTalentFlow."
            : "Every talent request Dijital Team is tracking for your organization."
        }
      />

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by designation or request code…"
            className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          />
        </div>
        <Select value={stage} onChange={(e) => setStage(e.target.value)} className="sm:w-48">
          <option value="">All stages</option>
          {CANONICAL_STAGES.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="sm:w-48">
          <option value="">All statuses</option>
          {LIFECYCLE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && <LoadingState label="Loading requests…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && (
        <EmptyState
          title="No requests found"
          description="Try adjusting your search or filters."
        />
      )}
      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((r) => (
            <RequestCard key={r.id} request={r} showClient={scope.isStaff} />
          ))}
        </div>
      )}
    </div>
  );
}
