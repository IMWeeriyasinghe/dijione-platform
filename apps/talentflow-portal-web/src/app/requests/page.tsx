"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from "@dijione/design-system";

import { listRequests } from "@/lib/api";

export default function RequestsPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["external-requests"],
    queryFn: () => listRequests(),
  });

  if (isLoading) return <LoadingState label="Loading requests…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-dt-text-primary">Your requests</h2>
        <p className="text-sm text-dt-text-secondary">
          Every talent request Dijital Team is running for your team.
        </p>
      </div>

      {data.length === 0 ? (
        <EmptyState
          title="No requests yet"
          description="When Dijital Team starts sourcing for a role, it will appear here."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((r) => (
            <li key={r.id}>
              <Link
                href={`/requests/${r.id}`}
                className="block rounded-xl border border-dt-border bg-dt-surface p-4 hover:border-dt-orange"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-medium text-dt-text-primary">{r.designation}</span>
                    <span className="ml-2 text-xs text-dt-text-secondary">{r.request_code}</span>
                  </div>
                  <StatusBadge status={r.current_stage} />
                </div>
                <p className="mt-1 text-sm text-dt-text-secondary">{r.client_safe_status_text}</p>
                <div className="mt-2 flex items-center gap-3 text-xs text-dt-text-secondary">
                  <span>{r.location || "Location flexible"}</span>
                  <span>·</span>
                  <span>{r.active_application_count} candidate(s) in process</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
