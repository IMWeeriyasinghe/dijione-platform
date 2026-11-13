"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CANDIDATE_PAGE_SIZES, listCandidatesPaged } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { CandidatePagination } from "./CandidatePagination";

export const SEARCH_DEBOUNCE_MS = 300;
const DEFAULT_PAGE_SIZE = 12;

export function CandidatePoolView() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);

  // Debounce typing; a new search term always restarts at page 1 and keeps the page size.
  useEffect(() => {
    const next = searchInput.trim();
    if (next === search) return;
    const t = setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput, search]);

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["candidates", "paged", search, page, pageSize],
    queryFn: () => listCandidatesPaged({ search: search || undefined, page, page_size: pageSize }),
    // Keep the previous page visible only while paging/resizing the SAME
    // search; a new search term never shows the old term's results.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[2] === search ? previous : undefined,
  });

  const goTo = (p: number) => {
    setPage(p);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div>
      <PageHeader
        title="Candidate Pool"
        description="One master candidate profile, sourced from Lever and reusable across multiple client engagements."
      />

      <div className="relative mb-6 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by name or title…"
          aria-label="Search candidates"
          className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
        />
      </div>

      {isLoading && <LoadingState label="Loading candidates…" />}
      {isError && !data && <ErrorState onRetry={() => refetch()} />}
      {data && data.total === 0 && (
        <EmptyState
          icon={UserRound}
          title="No candidates found"
          description={
            search
              ? "No candidates match your search. Try a different name or title."
              : "Candidates appear here once they're sourced from Lever."
          }
        />
      )}
      {data && data.total > 0 && data.items.length === 0 && (
        <p className="mb-4 text-sm text-dt-text-secondary">
          This page is now empty — the candidate list has changed.{" "}
          <button type="button" className="underline" onClick={() => goTo(data.total_pages)}>
            Go to the last page
          </button>
        </p>
      )}
      {data && data.total > 0 && (
        <div aria-busy={isFetching} className={isFetching ? "opacity-70 transition-opacity" : undefined}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((c) => (
              <Link key={c.id} href={`/candidates/${c.id}`}>
                <Card className="flex h-full flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:shadow-md">
                  <div>
                    <p className="text-base font-semibold text-dt-text-primary">{c.full_name}</p>
                    <p className="text-sm text-dt-text-secondary">{c.professional_title || "—"}</p>
                  </div>
                  <StatusBadge status={c.availability_status} />
                  <div className="flex flex-wrap gap-1.5">
                    {c.skills.slice(0, 4).map((s) => (
                      <span key={s} className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs text-dt-text-primary">
                        {s}
                      </span>
                    ))}
                  </div>
                  <p className="mt-auto text-xs text-dt-text-secondary">
                    {c.applications.length} application{c.applications.length === 1 ? "" : "s"}
                  </p>
                </Card>
              </Link>
            ))}
          </div>
          {isError && (
            <p role="alert" className="mt-4 text-sm text-dt-danger">
              Couldn&apos;t load that page.{" "}
              <button type="button" className="underline" onClick={() => refetch()}>
                Try again
              </button>
            </p>
          )}
          <CandidatePagination
            page={Math.min(page, data.total_pages)}
            pageSize={pageSize}
            pageSizes={CANDIDATE_PAGE_SIZES}
            total={data.total}
            totalPages={data.total_pages}
            onPageChange={goTo}
            onPageSizeChange={(s) => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </div>
      )}
    </div>
  );
}
