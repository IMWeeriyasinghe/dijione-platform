"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { getCandidate } from "@/lib/api";
import { ErrorState, LoadingState } from "@dijione/design-system";
import { Card, CardContent } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";

export default function CandidateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const candidateId = Number(id);
  const { data: candidate, isLoading, isError, refetch } = useQuery({
    queryKey: ["candidate", candidateId],
    queryFn: () => getCandidate(candidateId),
  });

  if (isLoading) return <LoadingState label="Loading candidate…" />;
  if (isError || !candidate) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div className="mx-auto max-w-3xl">
      <Link
        href="/candidates"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
      >
        <ArrowLeft className="size-4" />
        Back to candidate pool
      </Link>

      <Card className="mb-6">
        <CardContent className="pt-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold text-dt-text-primary">{candidate.full_name}</h1>
              <p className="text-sm text-dt-text-secondary">{candidate.professional_title}</p>
            </div>
            <StatusBadge status={candidate.availability_status} />
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-dt-text-secondary">Email</dt>
              <dd className="font-medium text-dt-text-primary">{candidate.email}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Phone</dt>
              <dd className="font-medium text-dt-text-primary">{candidate.phone || "—"}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Location</dt>
              <dd className="font-medium text-dt-text-primary">{candidate.location || "—"}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Source</dt>
              <dd className="font-medium text-dt-text-primary">{candidate.source}</dd>
            </div>
          </dl>

          {candidate.summary && (
            <p className="mt-4 whitespace-pre-line text-sm text-dt-text-primary">{candidate.summary}</p>
          )}

          {candidate.skills.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {candidate.skills.map((s) => (
                <span key={s} className="rounded-full bg-dt-surface-warm px-2.5 py-1 text-xs text-dt-text-primary">
                  {s}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Applications ({candidate.applications.length})
      </h2>
      <p className="mb-4 text-xs text-dt-text-secondary">
        One candidate, many client engagements — the same profile is reused across requests (CLAUDE.md §19).
      </p>
      <div className="flex flex-col gap-3">
        {candidate.applications.map((app) => (
          <Card key={app.application_id} className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm font-semibold text-dt-text-primary">{app.designation}</p>
              <p className="text-xs text-dt-text-secondary">{app.client_name}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={app.current_stage} />
              <StatusBadge status={app.status} />
            </div>
          </Card>
        ))}
        {candidate.applications.length === 0 && (
          <p className="text-sm text-dt-text-secondary">No applications yet.</p>
        )}
      </div>
    </div>
  );
}
