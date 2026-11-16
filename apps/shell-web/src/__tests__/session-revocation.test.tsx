import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  AuthProvider,
  SESSION_ENDED_EVENT,
  getToken,
  msUntilRefresh,
  request,
  retryDelayMs,
  setToken,
  tokenExpiryMs,
  useAuth,
} from "@dijione/auth-client";

// D2: a revoked session is re-issued once and the request repeated; the token is
// refreshed before it runs out, with backoff on failure, and an expired token ends
// the session instead of being sent.
const USER = { id: 7, email: "p@example.com", full_name: "Pat", title: null, platform_role: "PLATFORM_USER",
  avatar_color: null, platform_permissions: [], module_roles: [] };

function jwtExpiringIn(ms: number, tag = "a") {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${b64({ alg: "HS256" })}.${b64({ exp: Math.floor((Date.now() + ms) / 1000), tag })}.sig`;
}

type Reply = { status: number; headers?: Record<string, string>; body?: unknown };
let script: Record<string, Reply[]>;
let log: string[];

function stubFetch() {
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    const auth = (init?.headers as Record<string, string> | undefined)?.Authorization ?? "";
    log.push(`${key} ${auth.slice(-6)}`);
    const queue = script[key];
    if (!queue || queue.length === 0) throw new TypeError("network down");
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    if (reply.status === -1) throw new TypeError("network down");
    return new Response(JSON.stringify(reply.body ?? { detail: "x" }), { status: reply.status, headers: reply.headers });
  }));
}

const REVOKED: Reply = { status: 401, headers: { "X-Auth-Error": "session_revoked" } };

beforeEach(() => {
  script = {};
  log = [];
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setToken(null);
});

describe("revoked session on a request", () => {
  it("re-issues the token once and repeats the request with it", async () => {
    setToken("old-token");
    script["GET /api/x"] = [REVOKED, { status: 200, body: { ok: true } }];
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: "new-token", user: USER } }];
    await expect(request("/api/x")).resolves.toEqual({ ok: true });
    expect(log).toEqual(["GET /api/x -token", "POST /api/auth/refresh -token", "GET /api/x -token"].map((l, i) =>
      i === 2 ? l.replace("-token", "-token") : l));
    expect(getToken()).toBe("new-token");
  });

  it("does not loop: a second revocation is reported as the error", async () => {
    setToken("old-token");
    script["GET /api/x"] = [REVOKED];
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: "new-token", user: USER } }];
    await expect(request("/api/x")).rejects.toMatchObject({ status: 401 });
    expect(log.filter((l) => l.startsWith("GET /api/x"))).toHaveLength(2);
    expect(log.filter((l) => l.startsWith("POST /api/auth/refresh"))).toHaveLength(1);
  });

  it("shares one refresh between concurrent requests", async () => {
    setToken("old-token");
    script["GET /api/a"] = [REVOKED, { status: 200, body: { a: 1 } }];
    script["GET /api/b"] = [REVOKED, { status: 200, body: { b: 1 } }];
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: "new-token", user: USER } }];
    await expect(Promise.all([request("/api/a"), request("/api/b")])).resolves.toEqual([{ a: 1 }, { b: 1 }]);
    expect(log.filter((l) => l.startsWith("POST /api/auth/refresh"))).toHaveLength(1);
  });

  it("ends the session when the refresh is refused (deactivated account)", async () => {
    setToken("old-token");
    const ended = vi.fn();
    window.addEventListener(SESSION_ENDED_EVENT, ended);
    script["GET /api/x"] = [REVOKED];
    script["POST /api/auth/refresh"] = [{ status: 401 }];
    await expect(request("/api/x")).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
    expect(ended).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_ENDED_EVENT, ended);
  });

  it("leaves other 401s alone (no refresh attempt)", async () => {
    setToken("old-token");
    script["GET /api/x"] = [{ status: 401 }];
    await expect(request("/api/x")).rejects.toMatchObject({ status: 401 });
    expect(log).toEqual(["GET /api/x -token"]);
  });

  it("keeps the token when the refresh cannot be reached", async () => {
    setToken("old-token");
    script["GET /api/x"] = [REVOKED];
    script["POST /api/auth/refresh"] = [{ status: -1 }];
    await expect(request("/api/x")).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBe("old-token");
  });
});

describe("timing helpers", () => {
  it("read the expiry and say when a refresh is due", () => {
    const token = jwtExpiringIn(20 * 60_000);
    expect(tokenExpiryMs(token)).toBeGreaterThan(Date.now());
    const wait = msUntilRefresh(token)!;
    expect(wait).toBeGreaterThan(4 * 60_000);
    expect(wait).toBeLessThanOrEqual(5 * 60_000);
    expect(msUntilRefresh(jwtExpiringIn(5 * 60_000))).toBe(0);
    expect(msUntilRefresh("not-a-jwt")).toBeNull();
  });

  it("back off 30 s, 60 s, then 2 minutes", () => {
    expect([0, 1, 2, 3, 9].map(retryDelayMs)).toEqual([30_000, 60_000, 120_000, 120_000, 120_000]);
  });
});

function Probe() {
  const { user, loading } = useAuth();
  return <p>{loading ? "loading" : user ? "signed-in" : "signed-out"}</p>;
}

async function mount(initialToken: string) {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  setToken(initialToken);
  render(<AuthProvider><Probe /></AuthProvider>);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
}

describe("proactive refresh", () => {
  it("refreshes before the token runs out, then schedules the next one", async () => {
    script["POST /api/auth/refresh"] = [
      { status: 200, body: { access_token: jwtExpiringIn(20 * 60_000, "first"), user: USER } },
      { status: 200, body: { access_token: jwtExpiringIn(60 * 60_000, "second"), user: USER } },
      { status: 200, body: { access_token: jwtExpiringIn(60 * 60_000, "third"), user: USER } },
    ];
    await mount(jwtExpiringIn(60 * 60_000, "start"));
    const afterLoad = log.length; // the refresh made when the application loaded
    await act(async () => { await vi.advanceTimersByTimeAsync(4 * 60_000); }); // 16 min left: not yet due
    expect(log.length).toBe(afterLoad);
    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 60_000); }); // under 15 min left: due
    expect(log.length).toBe(afterLoad + 1);
    await act(async () => { await vi.advanceTimersByTimeAsync(46 * 60_000); }); // the new token has 60 min
    expect(log.length).toBe(afterLoad + 2);
    expect(screen.getByText("signed-in")).toBeInTheDocument();
  });

  it("retries after a failure with backoff and keeps the person signed in", async () => {
    script["POST /api/auth/refresh"] = [
      { status: 200, body: { access_token: jwtExpiringIn(20 * 60_000, "first"), user: USER } },
      { status: -1 },
      { status: -1 },
      { status: 200, body: { access_token: jwtExpiringIn(60 * 60_000, "ok"), user: USER } },
    ];
    script["GET /api/auth/me"] = [{ status: -1 }];
    await mount(jwtExpiringIn(60 * 60_000, "start"));
    const refreshes = () => log.filter((l) => l.startsWith("POST /api/auth/refresh")).length;
    expect(refreshes()).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(5 * 60_000 + 10_000); }); // due at 5:00: fails
    expect(refreshes()).toBe(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(31_000); }); // retry after 30 s: fails
    expect(refreshes()).toBe(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(61_000); }); // retry after 60 s: succeeds
    expect(refreshes()).toBe(4);
    expect(screen.getByText("signed-in")).toBeInTheDocument();
  });

  it("ends the session instead of refreshing once the token has expired", async () => {
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: jwtExpiringIn(2 * 60_000, "short"), user: USER } }];
    await mount(jwtExpiringIn(60 * 60_000, "start"));
    const before = log.length;
    // A long sleep: the tab was suspended past expiry and wakes with nothing valid to refresh.
    vi.setSystemTime(Date.now() + 3 * 60 * 60_000);
    await act(async () => {
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(log.length).toBe(before);
    expect(getToken()).toBeNull();
    expect(screen.getByText("signed-out")).toBeInTheDocument();
  });

  it("stops refreshing when a refresh no longer extends the token (session limit reached)", async () => {
    const capped = jwtExpiringIn(10 * 60_000, "capped"); // under the 15-minute lead, and refresh cannot extend it
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: capped, user: USER } }];
    await mount(capped);
    await act(async () => { await vi.advanceTimersByTimeAsync(9 * 60_000); });
    const refreshes = log.filter((l) => l.startsWith("POST /api/auth/refresh")).length;
    expect(refreshes).toBeLessThanOrEqual(2); // the load, then one scheduled try; never a loop
  });

  it("a token whose expiry cannot be read gets no timer and no error", async () => {
    script["POST /api/auth/refresh"] = [{ status: 200, body: { access_token: "opaque-token", user: USER } }];
    await mount("opaque-old");
    const before = log.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(24 * 60 * 60_000); });
    expect(log.length).toBe(before);
    expect(screen.getByText("signed-in")).toBeInTheDocument();
  });
});
