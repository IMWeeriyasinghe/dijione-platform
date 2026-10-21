// On-site DTOs — mirror onsite-api responses. Module-local (rule 6).

export type FeedState = "FRESH" | "DELAYED" | "STALE" | "SOURCE_UNAVAILABLE" | "NOT_SYNCED";

export type SyncRun = {
  run_id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
  trigger_type: string;
  requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  events_read: number;
  events_inserted: number;
  events_existing: number;
  sites_discovered?: number;
  high_water_received_utc: string | null;
  source_unavailable: boolean;
  error_summary: string | null;
};

export type AgentDetail = {
  agent_version: string | null;
  health_reason: string | null;
  source_epoch: number;
  high_water_id: number | null;
  source_connected: boolean;
  pending_count: number;
  dead_letter_count: number;
  oldest_pending_age_seconds: number | null;
  last_error: string | null;
  last_delivery_utc: string | null;
};

export type SiteFreshness = {
  site_id: string;
  feed_state: FeedState;
  latest_received_utc: string | null;
  latest_punch_utc: string | null;
  agent_heartbeat_utc: string | null;
  agent_health: string | null;
  agent?: AgentDetail;
};

export type ReconciliationRow = {
  site_id: string;
  source_epoch: number;
  source_count: number;
  mirror_count: number;
  source_max_received_utc: string | null;
  mirror_max_received_utc: string | null;
  in_sync: boolean;
};

export type Freshness = {
  last_successful_sync_at: string | null;
  latest_run: SyncRun | null;
  sites: SiteFreshness[];
};

export type SiteHealth = Freshness & { reconciliation: ReconciliationRow[] };

export type SyncAccepted = { run_id: string; status: string; started: boolean; message: string };

export type OnsiteSite = {
  site_id: string;
  enabled: boolean;
  label: string | null;
  display_name: string | null;
  time_zone: string | null;
  source_active: boolean | null;
  expected_location_values: string | null;
  last_seen_at: string | null;
};

export type IdentityClass =
  | "MATCHED_ACTIVE"
  | "MATCHED_INACTIVE"
  | "MATCHED_BEFORE_HIRE"
  | "AMBIGUOUS"
  | "UNMATCHED";

export type IdentityRow = {
  emp_code: string;
  identity_class: IdentityClass | null;
  event_count: number;
  first_seen: string;
  last_seen: string;
  matches: { bamboohr_id: string; display_name: string | null; employment_status: string | null; department: string | null }[];
};

export type IdentityReport = {
  directory_available: boolean;
  summary: Record<string, number>;
  rows: IdentityRow[];
};
