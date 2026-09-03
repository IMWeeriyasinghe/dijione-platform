"use client";

import { SYNC_TERMINAL_STATUSES } from "@dijione/contracts";
import { Button, Card } from "@dijione/design-system";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  getRecruitmentFreshness,
  getRecruitmentSyncRun,
  listRecruitmentPostings,
  requestRecruitmentSync,
} from "@/lib/api";

const NEEDS_REVIEW = new Set([
  "UNKNOWN_CLIENT_IDENTIFIER",
  "AMBIGUOUS_MULTIPLE_TAGS",
  "AMBIGUOUS_CLIENT_NAME",
  "MALFORMED_TAG",
  "CONFLICT_MANUAL_OVERRIDE",
]);

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleString();
}

/**
 * Recruitment Source (Lever) freshness + on-demand sync for internal TA
 * staff. The browser talks to talent-api only; talent-api talks to the
 * Recruitment Source. Indeterminate progress — the backend has no real
 * percentage, so we never fake one.
 */
export function RecruitmentSyncStatus() {
  const qc = useQueryClient();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const freshness = useQuery({
    queryKey: ["recruitment-freshness"],
    queryFn: getRecruitmentFreshness,
    refetchInterval: activeRunId ? false : 60_000,
  });

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const startPolling = (runId: string) => {
    stopPolling();
    setActiveRunId(runId);
    let ticks = 0;
    pollRef.current = setInterval(async () => {
      ticks += 1;
      try {
        const { run } = await getRecruitmentSyncRun(runId);
        if (run && SYNC_TERMINAL_STATUSES.includes(run.status)) {
          stopPolling();
          setActiveRunId(null);
          setFlash(
            run.status === "FAILED"
              ? "Sync failed — please try again shortly."
              : `Recruitment data updated · ${run.records_read} records checked.`,
          );
          setTimeout(() => setFlash(null), 6000);
          await freshness.refetch();
          qc.invalidateQueries({ queryKey: ["ta-dashboard"] });
        }
      } catch {
        /* transient — keep polling until the safety timeout */
      }
      if (ticks > 60) {
        stopPolling();
        setActiveRunId(null);
      }
    }, 3000);
  };

  useEffect(() => () => stopPolling(), []);

  const syncNow = useMutation({
    mutationFn: requestRecruitmentSync,
    onSuccess: (res) => {
      setFlash(null);
      startPolling(res.run_id);
    },
  });

  const postings = useQuery({
    queryKey: ["recruitment-postings"],
    queryFn: () => listRecruitmentPostings(),
    refetchInterval: activeRunId ? false : 120_000,
  });
  const needsReview = (postings.data ?? []).filter(
    (p) => p.mapping_status !== "VERIFIED" && NEEDS_REVIEW.has(p.resolution_status),
  ).length;

  const syncing = Boolean(activeRunId) || syncNow.isPending;
  const latest = freshness.data?.latest_run;
  const lastOk = freshness.data?.last_successful_sync_at ?? null;

  let statusLine: string;
  if (syncing) statusLine = "Syncing recruitment data…";
  else if (latest?.status === "FAILED") statusLine = "Last sync failed";
  else if (lastOk) statusLine = "Up to date";
  else statusLine = "Not yet synced";

  return (
    <Card className="mb-6 flex flex-wrap items-center justify-between gap-3 p-4">
      <div>
        <p className="text-sm font-semibold text-dt-text-primary">Recruitment data (Lever)</p>
        <p className="text-xs text-dt-text-secondary">
          Last synced: {relativeTime(lastOk)} · {statusLine}
        </p>
        {/* Truthful, not a live guarantee: this environment has no way to
            prove a scheduler is currently running, so we state the
            configured schedule as configuration — never "Automatic sync:
            Active" without a real runtime signal (plan §D). */}
        <p className="text-xs text-dt-text-secondary">
          Sync schedule: every 6 h (runs automatically in deployed environments)
        </p>
        {needsReview > 0 && (
          <Link
            href="/postings"
            className="mt-1 block text-xs font-medium text-dt-warning underline underline-offset-2"
          >
            {needsReview} posting{needsReview === 1 ? "" : "s"} need client mapping review →
          </Link>
        )}
        {flash && <p className="mt-1 text-xs text-dt-success">{flash}</p>}
      </div>
      <Button
        type="button"
        variant="secondary"
        disabled={syncing}
        onClick={() => syncNow.mutate()}
      >
        <RefreshCw className={`mr-2 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
        {syncing ? "Syncing…" : "Sync now"}
      </Button>
    </Card>
  );
}
