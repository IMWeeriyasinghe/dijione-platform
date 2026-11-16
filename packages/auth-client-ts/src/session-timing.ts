// Timing helpers for session refresh. They read the token's expiry only to decide
// WHEN to refresh; the server remains the authority on whether a token is valid.

/** Refresh when this much lifetime or less remains. */
export const REFRESH_LEAD_MS = 15 * 60 * 1000;

/** Scheduled refreshes are never closer together than this. */
export const MIN_REFRESH_GAP_MS = 30_000;

const RETRY_STEPS_MS = [30_000, 60_000, 120_000];

export function tokenExpiryMs(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = JSON.parse(json).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export function isExpired(token: string, now = Date.now()): boolean {
  const expiry = tokenExpiryMs(token);
  return expiry !== null && expiry <= now;
}

/** Milliseconds until a refresh is due (0 when due now); null when the token's expiry cannot be read. */
export function msUntilRefresh(token: string, now = Date.now(), lead = REFRESH_LEAD_MS): number | null {
  const expiry = tokenExpiryMs(token);
  return expiry === null ? null : Math.max(0, expiry - lead - now);
}

/** Backoff after a failed refresh: 30 s, 60 s, then every 2 minutes. */
export function retryDelayMs(attempt: number): number {
  return RETRY_STEPS_MS[Math.min(attempt, RETRY_STEPS_MS.length - 1)];
}
