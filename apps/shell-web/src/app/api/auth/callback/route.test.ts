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
    expect(html).toContain('location.replace("/")');
  });
});
