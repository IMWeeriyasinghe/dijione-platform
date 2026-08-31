// sync
// The DijiOne standard source-sync framework (recruitment-api / people-api
// scheduled+ad-hoc reconciliation run state and freshness).
// Published contract: a breaking change to a shape here needs a version bump
// (packages/contracts's own package.json), since every *-web app imports it.

// --- DijiOne standard source-sync framework -----------------------------
export type SyncStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
export type SyncTriggerType = "SCHEDULED" | "AD_HOC";

export const SYNC_TERMINAL_STATUSES: SyncStatus[] = ["SUCCEEDED", "PARTIAL", "FAILED"];

export type SyncRunSummary = {
  run_id: string;
  provider: string;
  status: SyncStatus;
  trigger_type: SyncTriggerType;
  requested_by_application: string;
  requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  records_read: number;
  records_created: number;
  records_updated: number;
  records_unchanged: number;
  error_summary: string | null;
};

export type SourceFreshness = {
  provider: string;
  last_successful_sync_at: string | null;
  latest_run: SyncRunSummary | null;
};
