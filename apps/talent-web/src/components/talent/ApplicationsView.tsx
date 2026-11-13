"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { listApplicationsPaged, updateApplicationVisibility } from "@/lib/api";
import { TABLE_PAGE_SIZES, keepPageWhile, useDebouncedSearch, usePaging } from "@/lib/paging";
import { TalentPagination } from "./TalentPagination";
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
  const paging = usePaging(TABLE_PAGE_SIZES[0]);
  const { input, setInput, search } = useDebouncedSearch(paging.reset, initialSearch);
  // Status filter (e.g. the Operations Dashboard's "Offers in Progress"
  // click-through, ?status=OFFER) is applied server-side, including Lever
  // offers carried as stage=OFFER, so totals and pages are exact.
  const [statusFilter, setStatusFilter] = useState(initialStatus);
  const [shareError, setShareError] = useState(false);
  const filterKey = [search, statusFilter];
  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["applications", "paged", ...filterKey, paging.page, paging.pageSize],
    queryFn: () =>
      listApplicationsPaged({
        search: search || undefined,
        status_filter: statusFilter || undefined,
        page: paging.page,
        page_size: paging.pageSize,
      }),
    placeholderData: keepPageWhile((k) => JSON.stringify(k.slice(2, 4)) === JSON.stringify(filterKey)),
  });
  const rows = data?.items;

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
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Search applications"
            placeholder="Search by designation…"
            className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          />
        </div>
        {statusFilter && (
          <button
            type="button"
            onClick={() => {
              setStatusFilter("");
              paging.reset();
            }}
            className="flex items-center gap-1.5 rounded-full border border-dt-orange/30 bg-dt-surface-warm px-3 py-1 text-xs font-medium text-dt-burnt-orange"
          >
            Status: {statusFilter}
            <span aria-hidden>×</span>
          </button>
        )}
      </div>

      {isLoading && <LoadingState label="Loading applications…" />}
      {isError && !data && <ErrorState onRetry={() => refetch()} />}
      {shareError && (
        <p role="alert" className="mb-3 text-sm text-dt-danger">
          Candidate sharing could not be updated. Please try again.
        </p>
      )}
      {data && data.total === 0 && <EmptyState title="No applications found" />}
      {data && data.total > 0 && rows && rows.length === 0 && (
        <p className="mb-4 text-sm text-dt-text-secondary">
          This page is now empty — the list has changed.{" "}
          <button type="button" className="underline" onClick={() => paging.setPage(data.total_pages)}>
            Go to the last page
          </button>
        </p>
      )}

      {rows && rows.length > 0 && (
        <div aria-busy={isFetching} className={isFetching ? "opacity-70 transition-opacity" : undefined}>
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
                        const box = e.target;
                        setShareError(false);
                        try {
                          await updateApplicationVisibility(app.id, box.checked);
                          invalidate();
                        } catch {
                          box.checked = !box.checked;
                          setShareError(true);
                        }
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
        </div>
      )}
      {data && data.total > 0 && (
        <>
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
            pageSizes={TABLE_PAGE_SIZES}
            total={data.total}
            totalPages={data.total_pages}
            onPageChange={(p) => {
              paging.setPage(p);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            onPageSizeChange={paging.setPageSize}
            noun={["application", "applications"]}
          />
        </>
      )}
    </div>
  );
}
