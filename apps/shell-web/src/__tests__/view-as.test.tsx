import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  AuthProvider,
  VIEW_AS_ENDED_EVENT,
  endViewAsLocally,
  exitViewAs,
  getStaffToken,
  getToken,
  getViewAsSession,
  request,
  setToken,
  setViewAsSession,
  startViewAs,
  useAuth,
} from "@dijione/auth-client";

// A read-only View-as session lives in one tab (sessionStorage) beside the administrator's own session
// (localStorage). Every request in that tab carries the View-as token; the staff token is never replaced,
// refreshed or cleared by it.
const EMPLOYEE = { id: 7, email: "ta@example.com", full_name: "Tara Employee", title: null, platform_role: "PLATFORM_USER",
  avatar_color: null, platform_permissions: [], module_roles: [],
  view_as: { session_id: "S-1", expires_at: "2099-01-01T00:00:00Z", actor_id: 1, actor_name: "Ada Admin", read_only: true } };

const SESSION = { token: "view-as-token", sessionId: "S-1", targetName: "Tara Employee", targetEmail: "ta@example.com",
  expiresAt: new Date(Date.now() + 20 * 60_000).toISOString(), returnTo: "/admin/users/7" };

type Reply = { status: number; headers?: Record<string, string>; body?: unknown };
let script: Record<string, Reply>;
let log: string[];
let assign: ReturnType<typeof vi.fn>;

beforeEach(() => {
  script = {};
  log = [];
  assign = vi.fn();
  Object.defineProperty(window, "location", { value: { ...window.location, assign, pathname: "/admin/users/7", search: "" }, writable: true });
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const h = init?.headers;
    const auth = (h instanceof Headers ? h.get("Authorization") : (h as Record<string, string> | undefined)?.Authorization) ?? "";
    log.push(`${init?.method ?? "GET"} ${path} ${auth.replace("Bearer ", "")}`);
    const reply = script[`${init?.method ?? "GET"} ${path}`];
    if (!reply) throw new TypeError("network down");
    return new Response(JSON.stringify(reply.body ?? { detail: "x" }), { status: reply.status, headers: reply.headers });
  }));
  window.localStorage.clear();
  window.sessionStorage.clear();
  setToken("staff-token");
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("which token a tab uses", () => {
  it("uses the staff token normally and the View-as token only inside a View-as session", () => {
    expect(getToken()).toBe("staff-token");
    setViewAsSession(SESSION);
    expect(getToken()).toBe("view-as-token");
    expect(getStaffToken()).toBe("staff-token"); // untouched
    endViewAsLocally();
    expect(getToken()).toBe("staff-token");
  });

  it("ignores an expired View-as session", () => {
    setViewAsSession({ ...SESSION, expiresAt: new Date(Date.now() - 1000).toISOString() });
    expect(getViewAsSession()).toBeNull();
    expect(getToken()).toBe("staff-token");
  });

  it("keeps the View-as token in this tab's sessionStorage, never in localStorage", () => {
    setViewAsSession(SESSION);
    expect(window.localStorage.getItem("dijione.viewAs")).toBeNull();
    expect(JSON.stringify(Object.entries(window.localStorage))).not.toContain("view-as-token");
  });
});

describe("starting and leaving", () => {
  it("starts with the staff token, switches this tab to the session and goes to the home page", async () => {
    script["POST /api/admin/view-as"] = { status: 201, body: {
      access_token: "view-as-token", session_id: "S-1", expires_at: SESSION.expiresAt,
      target: { id: 7, full_name: "Tara Employee", email: "ta@example.com", title: null } } };
    await startViewAs(7, "/admin/users/7");
    expect(log).toEqual(["POST /api/admin/view-as staff-token"]);
    expect(getToken()).toBe("view-as-token");
    expect(getStaffToken()).toBe("staff-token");
    expect(getViewAsSession()?.returnTo).toBe("/admin/users/7");
    expect(assign).toHaveBeenCalledWith("/");
  });

  it("reports why it could not start and changes nothing", async () => {
    script["POST /api/admin/view-as"] = { status: 404, body: { detail: "That user cannot be viewed" } };
    await expect(startViewAs(7, "/x")).rejects.toMatchObject({ status: 404, message: "That user cannot be viewed" });
    expect(getViewAsSession()).toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });

  it("ends the session on the server with the staff token, forgets it and returns the administrator", async () => {
    setViewAsSession(SESSION);
    script["POST /api/admin/view-as/S-1/end"] = { status: 200, body: { session_id: "S-1", ended: true } };
    await exitViewAs();
    expect(log).toEqual(["POST /api/admin/view-as/S-1/end staff-token"]);
    expect(getViewAsSession()).toBeNull();
    expect(getStaffToken()).toBe("staff-token");
    expect(assign).toHaveBeenCalledWith("/admin/users/7");
  });

  it("still leaves when the server cannot be reached", async () => {
    setViewAsSession(SESSION);
    await exitViewAs();
    expect(getViewAsSession()).toBeNull();
    expect(assign).toHaveBeenCalledWith("/admin/users/7");
  });
});

describe("requests inside a View-as session", () => {
  it("carry the View-as token", async () => {
    setViewAsSession(SESSION);
    script["GET /api/x"] = { status: 200, body: { ok: true } };
    await request("/api/x");
    expect(log).toEqual(["GET /api/x view-as-token"]);
  });

  it("a 401 ends the View-as session but not the administrator's own, and is never refreshed", async () => {
    setViewAsSession(SESSION);
    const ended = vi.fn();
    window.addEventListener(VIEW_AS_ENDED_EVENT, ended);
    script["GET /api/x"] = { status: 401, headers: { "X-Auth-Error": "session_revoked" } };
    await expect(request("/api/x")).rejects.toBeInstanceOf(ApiError);
    expect(log.some((l) => l.includes("/api/auth/refresh"))).toBe(false);
    expect(getViewAsSession()).toBeNull();
    expect(getStaffToken()).toBe("staff-token");
    expect(ended).toHaveBeenCalledTimes(1);
    window.removeEventListener(VIEW_AS_ENDED_EVENT, ended);
  });

  it("a refused change reads as a plain read-only message and leaves the session alone", async () => {
    setViewAsSession(SESSION);
    script["POST /api/x"] = { status: 403, headers: { "X-Auth-Error": "view_as_read_only" },
      body: { detail: "This is a read-only View-as session: changes are not allowed" } };
    await expect(request("/api/x", { method: "POST" })).rejects.toMatchObject({ status: 403, message: /read-only View-as/ });
    expect(getViewAsSession()).not.toBeNull();
  });
});

function Probe() {
  const { user, loading } = useAuth();
  return <p>{loading ? "loading" : user ? `user:${user.full_name}` : "signed-out"}</p>;
}

describe("the provider in a View-as tab", () => {
  it("shows the employee and the banner, reads only /me, and never refreshes", async () => {
    setViewAsSession(SESSION);
    script["GET /api/auth/me"] = { status: 200, body: EMPLOYEE };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("user:Tara Employee")).toBeInTheDocument();
    const banner = await screen.findByTestId("view-as-banner");
    expect(banner).toHaveTextContent("Read-only View as Tara Employee");
    expect(banner).toHaveTextContent("Ada Admin");
    expect(log).toEqual(["GET /api/auth/me view-as-token"]);
  });

  it("shows no banner in an ordinary session", async () => {
    script["POST /api/auth/refresh"] = { status: 200, body: { access_token: "staff-token", user: { ...EMPLOYEE, view_as: null } } };
    render(<AuthProvider><Probe /></AuthProvider>);
    await screen.findByText("user:Tara Employee");
    expect(screen.queryByTestId("view-as-banner")).toBeNull();
  });

  it("Exit View as ends the session and returns the administrator", async () => {
    setViewAsSession(SESSION);
    script["GET /api/auth/me"] = { status: 200, body: EMPLOYEE };
    script["POST /api/admin/view-as/S-1/end"] = { status: 200, body: { ended: true } };
    render(<AuthProvider><Probe /></AuthProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "Exit View as" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/admin/users/7"));
    expect(getViewAsSession()).toBeNull();
    expect(getStaffToken()).toBe("staff-token");
  });

  it("when the session is no longer valid it sends the administrator back and keeps their own session", async () => {
    setViewAsSession(SESSION);
    script["GET /api/auth/me"] = { status: 401, headers: { "X-Auth-Error": "view_as_ended" } };
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/admin/users/7"));
    expect(getStaffToken()).toBe("staff-token"); // never cleared by a View-as failure
  });

  it("Sign out in a View-as tab leaves the View-as session and keeps the administrator signed in", async () => {
    setViewAsSession(SESSION);
    script["GET /api/auth/me"] = { status: 200, body: EMPLOYEE };
    script["POST /api/admin/view-as/S-1/end"] = { status: 200, body: { ended: true } };
    function SignOut() {
      const { logout } = useAuth();
      return <button onClick={logout}>sign out</button>;
    }
    render(<AuthProvider><SignOut /></AuthProvider>);
    await userEvent.click(await screen.findByRole("button", { name: "sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/admin/users/7"));
    expect(getStaffToken()).toBe("staff-token");
  });

  it("states when the session ends", async () => {
    setViewAsSession(SESSION);
    script["GET /api/auth/me"] = { status: 200, body: EMPLOYEE };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByTestId("view-as-banner")).toHaveTextContent(/It ends at/);
  });

  it("does not schedule a refresh timer for a View-as token", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    setViewAsSession({ ...SESSION, expiresAt: new Date(Date.now() + 25 * 60_000).toISOString() });
    script["GET /api/auth/me"] = { status: 200, body: EMPLOYEE };
    render(<AuthProvider><Probe /></AuthProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60_000); });
    expect(log.filter((l) => l.includes("/api/auth/refresh"))).toHaveLength(0);
    vi.useRealTimers();
  });
});
