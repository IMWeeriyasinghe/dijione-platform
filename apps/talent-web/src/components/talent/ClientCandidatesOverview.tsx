"use client";

import { useQuery } from "@tanstack/react-query";
import { UserRound } from "lucide-react";
import Link from "next/link";
import { listRequestCandidates, listTalentRequests } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";

export function ClientCandidatesOverview() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["client-candidates-overview"],
    queryFn: async () => {
      const requests = await listTalentRequests();
      const perRequest = await Promise.all(
        requests.map(async (r) => ({
          request: r,
          candidates: await listRequestCandidates(r.id),
        }))
      );
      return perRequest.filter((r) => r.candidates.length > 0);
    },
  });

  return (
    <div>
      <PageHeader title="Candidates" description="Candidates shared with you across all of your talent requests." />

      {isLoading && <LoadingState label="Loading candidates…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && (
        <EmptyState
          icon={UserRound}
          title="No candidates shared yet"
          description="Talent Acquisition will share candidates here as they become ready for your review."
        />
      )}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-8">
          {data.map(({ request, candidates }) => (
            <section key={request.id}>
              <Link
                href={`/requests/${request.id}`}
                className="mb-3 inline-block text-sm font-semibold text-dt-text-primary hover:text-dt-burnt-orange"
              >
                {request.designation} <span className="text-dt-text-secondary">({request.request_code})</span>
              </Link>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {candidates.map((c) => (
                  <Card key={c.application_id} className="p-5">
                    <p className="text-base font-semibold text-dt-text-primary">{c.full_name}</p>
                    <p className="text-sm text-dt-text-secondary">{c.professional_title || "—"}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {c.skills.map((s) => (
                        <span key={s} className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs text-dt-text-primary">
                          {s}
                        </span>
                      ))}
                    </div>
                    <div className="mt-4">
                      <StatusBadge status={c.current_stage} />
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
