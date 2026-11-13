import { describe, expect, it } from "vitest";
import nextConfig, { DEV_PERSONA_PATHS } from "../../../next.config";

type Rewrite = { source: string; destination: string };

async function rewrites(): Promise<Rewrite[]> {
  const r = await nextConfig.rewrites!();
  return Array.isArray(r) ? (r as Rewrite[]) : [...(r.beforeFiles ?? []), ...(r.afterFiles ?? []), ...(r.fallback ?? [])];
}

describe("supplier portal public rewrites", () => {
  it("exposes only the two DEV persona paths under internal/dev, never a wildcard", async () => {
    const dev = (await rewrites()).filter((r) => r.source.includes("/internal/"));
    expect(dev.map((r) => r.source).sort()).toEqual(
      ["/api/birthday/internal/dev/supplier-login", "/api/birthday/internal/dev/supplier-users"],
    );
    expect(dev.every((r) => !r.source.includes(":path"))).toBe(true);
    expect([...DEV_PERSONA_PATHS]).toEqual(["supplier-users", "supplier-login"]);
  });

  it("never proxies the inbound-email injector or other internal routes", async () => {
    const sources = (await rewrites()).map((r) => r.source);
    expect(sources.some((s) => s.includes("inbound-email"))).toBe(false);
    expect(sources.some((s) => s.startsWith("/api/birthday/internal/") && !s.startsWith("/api/birthday/internal/dev/supplier-"))).toBe(false);
  });

  it("keeps the portal and supplier-auth prefixes the app depends on", async () => {
    const sources = (await rewrites()).map((r) => r.source);
    expect(sources).toContain("/api/birthday/portal/:path*");
    expect(sources).toContain("/api/birthday/supplier/auth/:path*");
  });
});
