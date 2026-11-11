import { describe, expect, it, vi, beforeEach } from "vitest";

// next/headers' cookies() needs a request-scoped store; mock it directly so
// this stays a pure unit test of the route handler's response shape.
const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { value: cookieStore.get(name) } : undefined),
    delete: (name: string) => cookieStore.delete(name),
  }),
}));

import { GET } from "./route";

// Regression test for the blank-page bug: every branch below used to emit
// `<script>` inside <head> with no explicit <body>, so `document.body` was
// still null when an error branch's `document.body.textContent = ...` ran
// synchronously — throwing "Cannot set properties of null" and leaving the
// user on a blank page instead of seeing the message or being redirected.
describe("GET /api/auth/callback", () => {
  beforeEach(() => {
    cookieStore.clear();
    vi.unstubAllGlobals();
  });

  async function bodyOf(request: Request): Promise<string> {
    const res = await GET(request);
    return res.text();
  }

  it("always emits an explicit <body> before the inline <script>, for every branch", async () => {
    // error_description branch
    const errBody = await bodyOf(new Request("https://shell-web.example/api/auth/callback?error_description=denied"));
    const scriptIndexErr = errBody.indexOf("<script>");
    const bodyIndexErr = errBody.indexOf("<body>");
    expect(bodyIndexErr).toBeGreaterThan(-1);
    expect(bodyIndexErr).toBeLessThan(scriptIndexErr);

    // missing code/state branch
    const missingBody = await bodyOf(new Request("https://shell-web.example/api/auth/callback"));
    expect(missingBody.indexOf("<body>")).toBeLessThan(missingBody.indexOf("<script>"));

    // missing flow cookie branch
    const noCookieBody = await bodyOf(
      new Request("https://shell-web.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(noCookieBody.indexOf("<body>")).toBeLessThan(noCookieBody.indexOf("<script>"));
  });

  it("error branch sets document.body.textContent to the failure reason (never blank)", async () => {
    const res = await GET(
      new Request("https://shell-web.example/api/auth/callback?error_description=access_denied"),
    );
    const html = await res.text();
    expect(html).toContain("document.body.textContent=");
    expect(html).toContain("Sign-in failed: access_denied");
  });

  it("cannot be broken out of by a crafted error value (reflected XSS)", async () => {
    const payload = "</script><script>alert(document.domain)</script>";
    const html = await bodyOf(
      new Request(
        `https://shell-web.example/api/auth/callback?error_description=${encodeURIComponent(payload)}`,
      ),
    );
    expect(html.match(/<script>/g)).toHaveLength(1);
    expect(html.match(/<\/script>/g)).toHaveLength(1);
    expect(html).not.toContain("alert(document.domain)</script>");
    expect(html).toContain("\\u003c/script\\u003e");
  });

  it("escapes a crafted detail returned by the token exchange", async () => {
    cookieStore.set("dijione_entra_flow", "flow");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "</script><img src=x>" }), { status: 400 })),
    );
    const html = await bodyOf(new Request("https://shell-web.example/api/auth/callback?code=abc&state=xyz"));
    expect(html.match(/<\/script>/g)).toHaveLength(1);
    expect(html).not.toContain("<img");
  });

  it("expired flow session shows a message instead of going blank", async () => {
    const html = await bodyOf(new Request("https://shell-web.example/api/auth/callback?code=abc&state=xyz"));
    expect(html).toContain("Sign-in session expired");
  });

  it("platform-api rejection (e.g. inactive-account 403) surfaces its detail message", async () => {
    cookieStore.set("dijione_entra_flow", "flow-token-value");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        json: async () => ({ detail: "Your account is not yet active in DijiOne." }),
      })),
    );

    const html = await bodyOf(
      new Request("https://shell-web.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(html).toContain("Your account is not yet active in DijiOne.");
    expect(html.indexOf("<body>")).toBeLessThan(html.indexOf("<script>"));
  });

  it("success path stores the token and redirects to /", async () => {
    cookieStore.set("dijione_entra_flow", "flow-token-value");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ access_token: "session-token-abc" }),
      })),
    );

    const html = await bodyOf(
      new Request("https://shell-web.example/api/auth/callback?code=abc&state=xyz"),
    );
    expect(html).toContain("localStorage.setItem");
    expect(html).toContain("session-token-abc");
    const script = /<script>([\s\S]*)<\/script>/.exec(html)![1];
    const landsOn = (stored: string | null) => {
      const replace = vi.fn();
      new Function("localStorage", "sessionStorage", "location", script)(
        { setItem() {} },
        { getItem: () => stored, removeItem() {} },
        { replace },
      );
      return replace.mock.calls[0][0];
    };
    expect(landsOn(null)).toBe("/");
    expect(landsOn("/atwork/management?x=1")).toBe("/atwork/management?x=1");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"]) {
      expect(landsOn(bad)).toBe("/");
    }
  });
});
