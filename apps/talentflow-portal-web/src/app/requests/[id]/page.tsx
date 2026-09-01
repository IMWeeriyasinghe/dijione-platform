"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "@dijione/design-system";

import { getRequest, listRequestCandidates } from "@/lib/api";

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const request = useQuery({
    queryKey: ["external-request", id],
    queryFn: () => getRequest(id),
    enabled: Number.isFinite(id),
  });
  const candidates = useQuery({
    queryKey: ["external-request-candidates", id],
    queryFn: () => listRequestCandidates(id),
    enabled: Number.isFinite(id),
  });

  if (request.isLoading) return <LoadingState label="Loading request…" />;
  if (request.isError || !request.data)
    return <ErrorState onRetry={() => request.refetch()} />;

  const r = request.data;

  return (
    <div>
      <Link
        href="/requests"
        className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
      >
        ← All requests
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold text-dt-text-primary">{r.designation}</h2>
          <p className="text-xs text-dt-text-secondary">{r.request_code}</p>
        </div>
        <StatusBadge status={r.current_stage} />
      </div>

      <Card className="mt-4 p-5">
        <p className="text-sm text-dt-text-secondary">{r.client_safe_status_text}</p>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-dt-cream">
          <div
            className="h-full rounded-full bg-dt-orange"
            style={{ width: `${Math.min(100, Math.max(0, r.progress_percent))}%` }}
          />
        </div>
        <ol className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {r.stage_timeline.map((s) => (
            <li
              key={s.stage}
              className={
                s.state === "CURRENT"
                  ? "font-semibold text-dt-burnt-orange"
                  : s.state === "DONE"
                    ? "text-dt-success"
                    : "text-dt-text-secondary"
              }
            >
              {s.state === "DONE" ? "✓ " : s.state === "CURRENT" ? "● " : "○ "}
              {s.label}
            </li>
          ))}
        </ol>
        {r.location && (
          <p className="mt-4 text-xs text-dt-text-secondary">Location: {r.location}</p>
        )}
      </Card>

      <h3 className="mt-8 mb-3 text-sm font-semibold text-dt-text-primary">
        Candidates shared with you
      </h3>
      {candidates.isLoading ? (
        <LoadingState label="Loading candidates…" />
      ) : candidates.isError || !candidates.data ? (
        <ErrorState onRetry={() => candidates.refetch()} />
      ) : candidates.data.length === 0 ? (
        <EmptyState
          title="No candidates to review yet"
          description="Dijital Team will share candidates here once they are ready for your review."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {candidates.data.map((c) => (
            <li
              key={c.application_id}
              className="rounded-xl border border-dt-border bg-dt-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-dt-text-primary">{c.full_name}</span>
                <StatusBadge status={c.current_stage} />
              </div>
              <p className="text-sm text-dt-text-secondary">{c.professional_title || "—"}</p>
              {c.skills.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.skills.map((skill) => (
                    <span
                      key={skill}
                      className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs text-dt-text-secondary"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              )}
              {c.relevant_experience_summary && (
                <p className="mt-2 text-sm text-dt-text-secondary">
                  {c.relevant_experience_summary}
                </p>
              )}
              {c.upcoming_interview_status && (
                <p className="mt-2 text-xs text-dt-burnt-orange">
                  Interview: {c.upcoming_interview_status}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
