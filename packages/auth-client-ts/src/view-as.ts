import type { ViewAsStartOut } from "@dijione/contracts";
import { ApiError, getStaffToken, getViewAsSession, setViewAsSession } from "./http";

// Starting and leaving a read-only View-as session. Both calls are made with the administrator's own
// staff token (never the View-as token), and the View-as token is kept for this tab only.

async function staffFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getStaffToken();
  return fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
}

async function failure(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = typeof body.detail === "string" ? body.detail : detail;
  } catch {
    // no JSON body
  }
  return new ApiError(res.status, detail);
}

/**
 * Begin viewing the application as an employee. On success this tab switches to the View-as session
 * and goes to the DijiOne home page, which then shows the employee's applications with the banner.
 * ``returnTo`` is where Exit View-as brings the administrator back to.
 */
export async function startViewAs(targetUserId: number, returnTo: string, goTo = "/"): Promise<void> {
  const res = await staffFetch("/api/admin/view-as", {
    method: "POST",
    body: JSON.stringify({ target_user_id: targetUserId }),
  });
  if (!res.ok) throw await failure(res);
  const started = (await res.json()) as ViewAsStartOut;
  setViewAsSession({
    token: started.access_token,
    sessionId: started.session_id,
    targetName: started.target.full_name,
    targetEmail: started.target.email,
    expiresAt: started.expires_at,
    returnTo,
  });
  if (typeof window !== "undefined") window.location.assign(goTo);
}

/** Leave the View-as session: end it on the server (best effort), forget it, and return the administrator. */
export async function exitViewAs(): Promise<void> {
  const session = getViewAsSession();
  if (!session) return;
  try {
    await staffFetch(`/api/admin/view-as/${encodeURIComponent(session.sessionId)}/end`, { method: "POST" });
  } catch {
    // The session also ends by itself when it expires; leaving must not depend on the network.
  }
  setViewAsSession(null);
  if (typeof window !== "undefined") window.location.assign(session.returnTo || "/");
}
