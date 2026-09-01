import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  currentSession,
  redeemToken,
  refreshSessionFromStoredToken,
} from "../external-auth";

const SESSION_KEY = "dijitalent-external-session";
const RAW_TOKEN_KEY = "dijitalent-external-raw";

function mockFetch(impl: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("redeemToken", () => {
  it("returns the access token on a 200", async () => {
    mockFetch(() => new Response(JSON.stringify({ access_token: "sess-xyz" }), { status: 200 }));
    expect(await redeemToken("raw-1")).toBe("sess-xyz");
  });

  it("returns null on any non-2xx (revoked / expired / rate limited)", async () => {
    mockFetch(() => new Response("nope", { status: 401 }));
    expect(await redeemToken("raw-1")).toBeNull();
    mockFetch(() => new Response("slow down", { status: 429 }));
    expect(await redeemToken("raw-1")).toBeNull();
  });

  it("returns null on a network error, never throws", async () => {
    mockFetch(() => {
      throw new Error("offline");
    });
    await expect(redeemToken("raw-1")).resolves.toBeNull();
  });
});

describe("refreshSessionFromStoredToken", () => {
  it("re-redeems the stored raw token and stores the fresh session", async () => {
    sessionStorage.setItem(RAW_TOKEN_KEY, "raw-42");
    mockFetch(() => new Response(JSON.stringify({ access_token: "fresh" }), { status: 200 }));

    const result = await refreshSessionFromStoredToken();

    expect(result).toBe("fresh");
    expect(currentSession()).toBe("fresh");
  });

  it("clears everything when the grant is no longer valid", async () => {
    sessionStorage.setItem(SESSION_KEY, "stale");
    sessionStorage.setItem(RAW_TOKEN_KEY, "raw-42");
    mockFetch(() => new Response("revoked", { status: 401 }));

    const result = await refreshSessionFromStoredToken();

    expect(result).toBeNull();
    expect(currentSession()).toBeNull();
    expect(sessionStorage.getItem(RAW_TOKEN_KEY)).toBeNull();
  });

  it("returns null with no stored raw token and makes no request", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect(await refreshSessionFromStoredToken()).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
