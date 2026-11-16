import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, getToken, setToken, useAuth } from "@dijione/auth-client";

// D2: the shared session provider re-issues the token when an application
// loads, so access granted or removed in the Admin Center applies without a
// new sign-in. Exercises the real provider against a stubbed fetch.
const USER = { id: 7, email: "p@example.com", full_name: "Pat", title: null, platform_role: "PLATFORM_USER",
  avatar_color: null, platform_permissions: [], module_roles: [] };
const GRANTED = { ...USER, module_roles: [{ module_key: "talent-flow", role: "TA_MEMBER", client_id: null, enabled: true }] };

type Reply = { status: number; body?: unknown };
let routes: Record<string, Reply | (() => Reply)>;
let calls: string[];

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <p>loading</p>;
  return <p>{user ? `signed-in:${user.module_roles.map((r) => r.module_key).join(",")}` : "signed-out"}</p>;
}

beforeEach(() => {
  calls = [];
  routes = {};
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    calls.push(`${key} ${(init?.headers as Record<string, string>).Authorization ?? ""}`);
    const route = routes[key];
    if (!route) throw new TypeError("network down");
    const reply = typeof route === "function" ? route() : route;
    return new Response(JSON.stringify(reply.body ?? { detail: "x" }), { status: reply.status });
  }));
  setToken("old-token");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setToken(null);
});

describe("session refresh on load", () => {
  it("replaces the token and shows access granted since sign-in", async () => {
    routes["POST /api/auth/refresh"] = { status: 200, body: { access_token: "new-token", user: GRANTED } };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed-in:talent-flow")).toBeInTheDocument();
    expect(getToken()).toBe("new-token");
    expect(calls).toEqual(["POST /api/auth/refresh Bearer old-token"]);
  });

  it("signs out when the session is no longer valid", async () => {
    routes["POST /api/auth/refresh"] = { status: 401 };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed-out")).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it.each([404, 503])("keeps the existing session when refresh is unavailable (%i)", async (status) => {
    routes["POST /api/auth/refresh"] = { status };
    routes["GET /api/auth/me"] = { status: 200, body: USER };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed-in:")).toBeInTheDocument();
    expect(getToken()).toBe("old-token");
  });

  it("does not restore a session that was signed out while the refresh was in flight", async () => {
    routes["POST /api/auth/refresh"] = () => {
      setToken(null);
      return { status: 200, body: { access_token: "new-token", user: USER } };
    };
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(calls).toHaveLength(1));
    await screen.findByText(/signed-/);
    expect(getToken()).toBeNull();
  });

  it("refreshes again when the tab is shown after five minutes, and survives a failed check", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    routes["POST /api/auth/refresh"] = { status: 200, body: { access_token: "t1", user: USER } };
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(await screen.findByText("signed-in:")).toBeInTheDocument();

    document.dispatchEvent(new Event("visibilitychange"));
    expect(calls).toHaveLength(1); // too soon

    vi.setSystemTime(Date.now() + 6 * 60 * 1000);
    routes["POST /api/auth/refresh"] = { status: 200, body: { access_token: "t2", user: GRANTED } };
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(await screen.findByText("signed-in:talent-flow")).toBeInTheDocument();
    expect(getToken()).toBe("t2");

    vi.setSystemTime(Date.now() + 6 * 60 * 1000);
    delete routes["POST /api/auth/refresh"]; // network failure on refresh and on /me
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(4));
    expect(screen.getByText("signed-in:talent-flow")).toBeInTheDocument();
    expect(getToken()).toBe("t2");
  });
});
