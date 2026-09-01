"use client";

import { useQuery } from "@tanstack/react-query";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "@dijione/design-system";

import { listInterviews } from "@/lib/api";

function fmt(value: string): string {
  const d = new Date(value);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function InterviewsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["external-interviews"],
    queryFn: listInterviews,
  });

  if (isLoading) return <LoadingState label="Loading interviews…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Interviews</h2>
        <p className="text-sm text-dt-text-secondary">
          Scheduled and completed interviews for your requests.
        </p>
      </div>

      {data.length === 0 ? (
        <EmptyState
          title="No interviews scheduled"
          description="Interviews for your candidates will show up here once they are booked."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((i) => (
            <li
              key={i.id}
              className="rounded-xl border border-dt-border bg-dt-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium text-dt-text-primary">{i.candidate_name}</span>
                  <span className="ml-2 text-sm text-dt-text-secondary">{i.designation}</span>
                </div>
                <StatusBadge status={i.status} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-dt-text-secondary">
                <span>{fmt(i.scheduled_at)}</span>
                <span>·</span>
                <span>{i.interview_type}</span>
                {i.meeting_link && (
                  <a
                    href={i.meeting_link}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-dt-burnt-orange underline underline-offset-2"
                  >
                    Join
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
