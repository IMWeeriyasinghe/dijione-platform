"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { listTalentRequests } from "@/lib/api";
import { useTalentScope } from "@dijione/auth-client";
import { PageHeader } from "@dijione/design-system";
import { Select } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { CANONICAL_STAGES, LIFECYCLE_STATUSES } from "@dijione/contracts";
import { stageLabel } from "@dijione/design-system";

// Matches DashboardService.ta_dashboard's own "active" definition
// (apps/talent-api/app/services/dashboard_service.py) exactly, so a
// dashboard widget's count and its click-through list agree. "active" is
// a frontend-only pseudo-filter — the API has no such status value, so it
// is applied client-side after an unfiltered fetch rather than sent as
// status_filter.
const ACTIVE_LIFECYCLE_STATUSES = new Set(["APPROVED", "IN_PROGRESS"]);

function RequestsPageInner() {
  const scope = useTalentScope();
  const searchParams = useSearchParams();
  const initialStatus = searchParams.get("status") ?? "";
  const initialClientId = searchParams.get("client_id");

  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState(initialStatus);

  const activeOnly = status === "active";
  const clientId = initialClientId ? Number(initialClientId) : undefined;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["talent-requests", search, stage, status, clientId],
    queryFn: () =>
      listTalentRequests({
        search: search || undefined,
        stage: stage || undefined,
        // "active" has no server-side meaning — filtered client-side below.
        status_filter: activeOnly ? undefined : status || undefined,
        client_id: clientId,
      }),
  });

  const rows = data && activeOnly
    ? data.filter((r) => ACTIVE_LIFECYCLE_STATUSES.has(r.lifecycle_status))
    : data;

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
          {activeOnly && <option value="active">Active (Approved + In Progress)</option>}
          {LIFECYCLE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && <LoadingState label="Loading requests…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {rows && rows.length === 0 && (
        <EmptyState
          title="No requests found"
          description="Try adjusting your search or filters."
        />
      )}
      {rows && rows.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((r) => (
            <RequestCard key={r.id} request={r} showClient={scope.isStaff} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function RequestsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <RequestsPageInner />
    </Suspense>
  );
}
