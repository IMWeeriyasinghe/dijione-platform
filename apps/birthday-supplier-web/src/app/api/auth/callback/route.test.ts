import { describe, expect, it, vi, beforeEach } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { value: cookieStore.get(name) } : undefined),
    delete: (name: string) => cookieStore.delete(name),
  }),
}));

import { GET } from "./route";

describe("GET /api/auth/callback (Supplier Portal)", () => {
  beforeEach(() => {
    cookieStore.clear();
    vi.unstubAllGlobals();
  });

  async function bodyOf(request: Request): Promise<string> {
    const res = await GET(request);
    return res.text();
  }

  it("redirects to the deep-linked order when the token exchange returns return_to", async () => {
    cookieStore.set("dijibirthday_supplier_flow", "flow-token-value");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ access_token: "session-token-abc", return_to: "/orders/42" }),
      })),
    );

    const html = await bodyOf(
      new Request("https://supplierportal.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(html).toContain("session-token-abc");
    expect(html).toContain('location.replace("/orders/42")');
  });

  it("falls back to portal home when the token exchange returns no return_to", async () => {
    cookieStore.set("dijibirthday_supplier_flow", "flow-token-value");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ access_token: "session-token-abc" }),
      })),
    );

    const html = await bodyOf(
      new Request("https://supplierportal.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(html).toContain('location.replace("/")');
  });

  it("never redirects to an attacker-supplied absolute URL even if birthday-api ever echoed one back", async () => {
    cookieStore.set("dijibirthday_supplier_flow", "flow-token-value");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          access_token: "session-token-abc",
          return_to: "https://evil.example.com/phish",
        }),
      })),
    );

    const html = await bodyOf(
      new Request("https://supplierportal.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(html).not.toContain("evil.example.com");
    expect(html).toContain('location.replace("/")');
  });

  it("error branch still shows the failure message (unaffected by the return_to change)", async () => {
    const html = await bodyOf(
      new Request("https://supplierportal.example/api/auth/callback?error_description=access_denied"),
    );
    expect(html).toContain("Sign-in failed: access_denied");
  });
});
