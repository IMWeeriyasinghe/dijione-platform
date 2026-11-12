import { afterEach, describe, expect, it } from "vitest";
import { dynamic, GET } from "../route";

// Round 3 — /api/meta exposes this container's real, runtime RELEASE_DATE
// (docs/platform/versioning.md). The `dynamic = "force-dynamic"` export is
// what proves this route is evaluated fresh per request rather than baked
// once at `next build` — asserted directly rather than trusted.

describe("/api/meta route (release metadata + runtime environment)", () => {
  const originalReleaseDate = process.env.RELEASE_DATE;
  const originalAppEnv = process.env.APP_ENV;
  afterEach(() => {
    if (originalReleaseDate === undefined) delete process.env.RELEASE_DATE;
    else process.env.RELEASE_DATE = originalReleaseDate;
    if (originalAppEnv === undefined) delete process.env.APP_ENV;
    else process.env.APP_ENV = originalAppEnv;
  });

  it("is registered as force-dynamic — never statically prerenderable", () => {
    expect(dynamic).toBe("force-dynamic");
  });

  it("returns the live RELEASE_DATE env var when set", async () => {
    process.env.RELEASE_DATE = "2026-09-14T10:42:00Z";
    const res = GET();
    const body = await res.json();
    expect(body.release_date).toBe("2026-09-14T10:42:00Z");
  });

  it("returns null, never a fabricated value, when RELEASE_DATE is unset", async () => {
    delete process.env.RELEASE_DATE;
    const res = GET();
    const body = await res.json();
    expect(body.release_date).toBeNull();
  });

  // is_production must be evaluated at REQUEST time, not baked at build
  // time — this platform promotes the exact same image digest
  // DEV -> UAT -> PROD, so a NEXT_PUBLIC_* build arg would be wrong the
  // moment that image ran in a different environment. force-dynamic (see
  // the "never statically prerenderable" test above) is what makes reading
  // process.env.APP_ENV here safe to do at all.
  it("reports is_production=true only when APP_ENV=prod", async () => {
    process.env.APP_ENV = "prod";
    let body = await GET().json();
    expect(body.is_production).toBe(true);

    process.env.APP_ENV = "development";
    body = await GET().json();
    expect(body.is_production).toBe(false);

    process.env.APP_ENV = "uat";
    body = await GET().json();
    expect(body.is_production).toBe(false);

    delete process.env.APP_ENV;
    body = await GET().json();
    expect(body.is_production).toBe(false);
  });
});
