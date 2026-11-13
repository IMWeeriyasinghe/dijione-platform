"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { listTalentRequestsPaged } from "@/lib/api";
import { CARD_PAGE_SIZES, keepPageWhile, useDebouncedSearch, usePaging } from "@/lib/paging";
import { TalentPagination } from "@/components/talent/TalentPagination";
import { useTalentScope } from "@dijione/auth-client";
import { PageHeader } from "@dijione/design-system";
import { Select } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { RequestCard } from "@/components/talent/RequestCard";
import { CANONICAL_STAGES, LIFECYCLE_STATUSES } from "@dijione/contracts";
import { stageLabel } from "@dijione/design-system";

// "active" (from the Operations Dashboard click-through) is resolved
// server-side by /requests/paged as APPROVED + IN_PROGRESS — the same
// definition as DashboardService.ta_dashboard — so totals and pages agree
// with the dashboard count.

function RequestsPageInner() {
  const scope = useTalentScope();
  const searchParams = useSearchParams();
  const initialStatus = searchParams.get("status") ?? "";
  const initialClientId = searchParams.get("client_id");

  const paging = usePaging(CARD_PAGE_SIZES[0]);
  const { input, setInput, search } = useDebouncedSearch(paging.reset);
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState(initialStatus);

  const activeOnly = status === "active";
  const clientId = initialClientId ? Number(initialClientId) : undefined;
  const filterKey = [search, stage, status, clientId];

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["talent-requests", "paged", ...filterKey, paging.page, paging.pageSize],
    queryFn: () =>
      listTalentRequestsPaged({
        search: search || undefined,
        stage: stage || undefined,
        status_filter: status || undefined,
        client_id: clientId,
        page: paging.page,
        page_size: paging.pageSize,
      }),
    placeholderData: keepPageWhile((k) => JSON.stringify(k.slice(2, 6)) === JSON.stringify(filterKey)),
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
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Search requests"
            placeholder="Search by designation or request code…"
            className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          />
        </div>
        <Select aria-label="Filter by stage" value={stage} onChange={(e) => { setStage(e.target.value); paging.reset(); }} className="sm:w-48">
          <option value="">All stages</option>
          {CANONICAL_STAGES.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
        <Select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); paging.reset(); }} className="sm:w-48">
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
      {isError && !data && <ErrorState onRetry={() => refetch()} />}
      {data && data.total === 0 && (
        <EmptyState
          title="No requests found"
          description="Try adjusting your search or filters."
        />
      )}
      {data && data.total > 0 && (
        <div aria-busy={isFetching} className={isFetching ? "opacity-70 transition-opacity" : undefined}>
          {data.items.length === 0 ? (
            <p className="mb-4 text-sm text-dt-text-secondary">
              This page is now empty — the list has changed.{" "}
              <button type="button" className="underline" onClick={() => paging.setPage(data.total_pages)}>
                Go to the last page
              </button>
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((r) => (
                <RequestCard key={r.id} request={r} showClient={scope.isStaff} />
              ))}
            </div>
          )}
          {isError && (
            <p role="alert" className="mt-4 text-sm text-dt-danger">
              Couldn&apos;t load that page.{" "}
              <button type="button" className="underline" onClick={() => refetch()}>
                Try again
              </button>
            </p>
          )}
          <TalentPagination
            page={Math.min(paging.page, data.total_pages)}
            pageSize={paging.pageSize}
            pageSizes={CARD_PAGE_SIZES}
            total={data.total}
            totalPages={data.total_pages}
            onPageChange={(p) => {
              paging.setPage(p);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onPageSizeChange={paging.setPageSize}
            noun={["request", "requests"]}
          />
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
