"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, EmptyState, ErrorState, LoadingState, StatusBadge } from "@dijione/design-system";

import { ApiError, getCandidateReview } from "@/lib/api";

export default function CandidateReviewPage() {
  const params = useParams<{ applicationId: string }>();
  const applicationId = Number(params.applicationId);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["external-candidate-review", applicationId],
    queryFn: () => getCandidateReview(applicationId),
    enabled: Number.isFinite(applicationId),
    retry: false,
  });

  if (isLoading) return <LoadingState label="Loading candidate…" />;

  if (error || !data) {
    // Server-side the 4-part invariant collapses every authorization
    // failure mode (wrong client, not yet shared with you, genuinely
    // unknown id) into an identical 404 — mirrored here as one generic,
    // non-retryable message with no hint of the real reason. A genuine
    // transient/server error is a different, retryable case.
    const notFound = error instanceof ApiError && error.status === 404;
    if (!notFound) return <ErrorState onRetry={() => refetch()} />;
    return (
      <div>
        <Link
          href="/requests"
          className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
        >
          ← Back to requests
        </Link>
        <div className="mt-4">
          <EmptyState
            title="Candidate not found"
            description="This candidate is no longer shared with you, or the link is no longer valid."
          />
        </div>
      </div>
    );
  }

  const c = data;

  return (
    <div>
      <Link
        href="/requests"
        className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
      >
        ← Back to requests
      </Link>

      <Card className="mt-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-dt-text-primary">{c.full_name}</h2>
            <p className="text-sm text-dt-text-secondary">{c.professional_title || "—"}</p>
          </div>
          <StatusBadge status={c.current_stage} />
        </div>

        {c.skills.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {c.skills.map((skill) => (
              <span
                key={skill}
                className="rounded-full bg-dt-surface-warm px-2.5 py-1 text-xs text-dt-text-secondary"
              >
                {skill}
              </span>
            ))}
          </div>
        )}

        {c.relevant_experience_summary && (
          <p className="mt-4 text-sm text-dt-text-secondary">{c.relevant_experience_summary}</p>
        )}

        {c.upcoming_interview_status && (
          <div className="mt-5 rounded-lg border border-dt-orange/25 bg-dt-surface-warm px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">
              Upcoming interview
            </p>
            <p className="mt-1 text-sm text-dt-text-primary">{c.upcoming_interview_status}</p>
          </div>
        )}
      </Card>
    </div>
  );
}
