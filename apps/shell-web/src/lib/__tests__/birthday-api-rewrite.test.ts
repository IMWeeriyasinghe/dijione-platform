import { describe, expect, it } from "vitest";
// Next's own bundled path-to-regexp — the matcher rewrites() sources compile with.
// @ts-expect-error -- Next ships this compiled module without type declarations.
import { pathToRegexp as untypedPathToRegexp } from "next/dist/compiled/path-to-regexp";
import nextConfig, { BIRTHDAY_API_PUBLIC_SOURCE } from "../../../next.config";

type Rewrite = { source: string; destination: string };
const pathToRegexp = untypedPathToRegexp as (source: string) => RegExp;

describe("shell /api/birthday forwarding", () => {
  const re = pathToRegexp(BIRTHDAY_API_PUBLIC_SOURCE);

  it.each([
    "/api/birthday/summary",
    "/api/birthday/orders",
    "/api/birthday/orders/12/timeline",
    "/api/birthday/suppliers/3/users/4/invite",
    "/api/birthday/admin/test-email-recipients",
    "/api/birthday/internalish", // only the exact internal/ segment is excluded
  ])("forwards public route %s", (path) => {
    expect(re.test(path)).toBe(true);
  });

  it.each([
    "/api/birthday/internal",
    "/api/birthday/internal/",
    "/api/birthday/internal/run-comms",
    "/api/birthday/internal/dev/inbound-email",
    "/api/birthday/internal/scan-runs/abc",
  ])("never forwards internal route %s", (path) => {
    expect(re.test(path)).toBe(false);
  });

  it("is the only /api/birthday rewrite, and keeps the captured path", async () => {
    const r = (await nextConfig.rewrites!()) as Rewrite[];
    const birthday = r.filter((x) => x.source.startsWith("/api/birthday"));
    expect(birthday).toHaveLength(1);
    expect(birthday[0].source).toBe(BIRTHDAY_API_PUBLIC_SOURCE);
    expect(birthday[0].destination.endsWith("/api/birthday/:path")).toBe(true);
  });
});
