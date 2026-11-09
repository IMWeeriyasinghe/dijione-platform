/** Shared Home status model. Every active module inherits it from its registry key. */

export type ModuleHealth = "CHECKING" | "HEALTHY" | "IDLE" | "STARTING" | "UNAVAILABLE" | "UNKNOWN";

/** Replica state from an authorized backend. None exists yet: a failed browser
 * request says nothing about replicas, so IDLE and STARTING need this evidence. */
export type ReplicaSignal = "SCALED_TO_ZERO" | "STARTING";

export const HEALTH_TIMEOUT_MS = 20_000; // long enough for a Container Apps cold start
export const STATUS_STALE_MS = 60_000;
export const STATUS_POLL_MS = 300_000; // every poll can wake a scaled-down service
const MAX_RETRIES = 2;

const SUMMARY_PATH_OVERRIDES: Record<string, string> = { "talent-flow": "/api/talent/summary" };

export function summaryPathFor(moduleKey: string): string {
  return SUMMARY_PATH_OVERRIDES[moduleKey] ?? `/api/${moduleKey}/summary`;
}

type FailureKind = "server-error" | "no-response" | "no-status";

function failureKind(error: unknown): FailureKind {
  const status = (error as { status?: unknown } | null)?.status;
  if (typeof status !== "number") return "no-response";
  return status >= 500 ? "server-error" : "no-status";
}

export function shouldRetryStatus(failureCount: number, error: unknown): boolean {
  return failureCount < MAX_RETRIES && failureKind(error) !== "no-status";
}

export function statusRetryDelay(attempt: number): number {
  return 5_000 * 3 ** attempt;
}

export function deriveModuleHealth(input: {
  isPending: boolean;
  isSuccess: boolean;
  error: unknown;
  signal?: ReplicaSignal;
}): ModuleHealth {
  if (input.isSuccess) return "HEALTHY";
  if (input.signal === "STARTING") return "STARTING";
  if (input.signal === "SCALED_TO_ZERO") return "IDLE";
  if (input.isPending) return "CHECKING";
  return failureKind(input.error) === "server-error" ? "UNAVAILABLE" : "UNKNOWN";
}

export const HEALTH_DISPLAY: Record<ModuleHealth, { label: string; dot: string; text: string; title?: string }> = {
  CHECKING: { label: "Checking…", dot: "bg-dt-text-secondary/40", text: "text-dt-text-secondary" },
  HEALTHY: { label: "Healthy", dot: "bg-dt-success", text: "font-medium text-dt-success" },
  IDLE: {
    label: "Idle",
    dot: "bg-dt-text-secondary/60",
    text: "font-medium text-dt-text-secondary",
    title: "This application is currently idle and may take a moment to start.",
  },
  STARTING: { label: "Starting…", dot: "bg-dt-info", text: "font-medium text-dt-info" },
  UNAVAILABLE: { label: "Unavailable", dot: "bg-dt-danger", text: "font-medium text-dt-danger" },
  UNKNOWN: {
    label: "Status not confirmed",
    dot: "bg-dt-text-secondary/40",
    text: "text-dt-text-secondary",
    title: "DijiOne could not confirm this application's status. You can still open it.",
  },
};
