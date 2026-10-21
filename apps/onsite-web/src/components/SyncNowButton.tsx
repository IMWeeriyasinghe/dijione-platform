"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@dijione/design-system";
import { getSyncRun, requestSync } from "@/lib/api";

const POLL_MS = 3_000;
const MAX_POLLS = 100; // bounded: ~5 minutes, then stop and let the 60s refresh take over

export function SyncNowButton({ onDone }: { onDone: () => void }) {
  const [runId, setRunId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const polls = useRef(0);

  useEffect(() => {
    if (!runId) return;
    polls.current = 0;
    const timer = setInterval(async () => {
      polls.current += 1;
      try {
        const run = await getSyncRun(runId);
        if (run.status !== "QUEUED" && run.status !== "RUNNING") {
          setMessage(run.status === "SUCCEEDED"
            ? `Sync complete — ${run.events_inserted} new event(s), ${run.events_existing} already mirrored.`
            : run.source_unavailable ? "Source unavailable — the mirror was left unchanged." : "Sync failed — the mirror was left unchanged.");
          setRunId(null);
          onDone();
        }
      } catch {
        /* keep polling until bounded */
      }
      if (polls.current >= MAX_POLLS) setRunId(null);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runId, onDone]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        loading={runId !== null}
        disabled={runId !== null}
        onClick={async () => {
          setMessage(null);
          const accepted = await requestSync();
          setRunId(accepted.run_id);
          if (!accepted.started) setMessage("A sync is already running — following it.");
        }}
      >
        Sync now
      </Button>
      {runId && <span className="text-sm text-dt-text-secondary">Syncing…</span>}
      {message && <span className="text-sm text-dt-text-secondary">{message}</span>}
    </div>
  );
}
