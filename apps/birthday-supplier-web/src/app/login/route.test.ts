import { describe, expect, it, vi, beforeEach } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    set: (name: string, value: string) => cookieStore.set(name, value),
  }),
}));

import { GET } from "./route";

describe("GET /login (Supplier Portal)", () => {
  beforeEach(() => {
    cookieStore.clear();
    vi.unstubAllGlobals();
  });

  it("forwards a safe return_to to birthday-api's login-url endpoint", async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      const u = new URL(url);
      expect(u.pathname).toBe("/api/birthday/supplier/auth/login-url");
      expect(u.searchParams.get("return_to")).toBe("/orders/42");
      return {
        ok: true,
        json: async () => ({ authorize_url: "https://login.microsoftonline.com/authorize", flow_token: "ft" }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(new Request("https://supplierportal.example/login?return_to=%2Forders%2F42"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(res.status).toBe(307); // NextResponse.redirect default
  });

  it("drops an unsafe return_to (never forwarded to birthday-api)", async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      const u = new URL(url);
      expect(u.searchParams.has("return_to")).toBe(false);
      return {
        ok: true,
        json: async () => ({ authorize_url: "https://login.microsoftonline.com/authorize", flow_token: "ft" }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    await GET(
      new Request("https://supplierportal.example/login?return_to=https%3A%2F%2Fevil.example.com"),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("works with no return_to at all", async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      const u = new URL(url);
      expect(u.searchParams.has("return_to")).toBe(false);
      return {
        ok: true,
        json: async () => ({ authorize_url: "https://login.microsoftonline.com/authorize", flow_token: "ft" }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    const res = await GET(new Request("https://supplierportal.example/login"));
    expect(res.status).toBe(307);
  });
});
