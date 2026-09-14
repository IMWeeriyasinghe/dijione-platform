import { afterEach, describe, expect, it } from "vitest";
import { dynamic, GET } from "../route";

// Round 3 — /api/meta exposes this container's real, runtime RELEASE_DATE
// (docs/platform/versioning.md). The `dynamic = "force-dynamic"` export is
// what proves this route is evaluated fresh per request rather than baked
// once at `next build` — asserted directly rather than trusted.

describe("/api/meta route (release metadata)", () => {
  const original = process.env.RELEASE_DATE;
  afterEach(() => {
    if (original === undefined) delete process.env.RELEASE_DATE;
    else process.env.RELEASE_DATE = original;
  });

  it("is registered as force-dynamic — never statically prerenderable", () => {
    expect(dynamic).toBe("force-dynamic");
  });

  it("returns the live RELEASE_DATE env var when set", async () => {
    process.env.RELEASE_DATE = "2026-09-14T10:42:00Z";
    const res = GET();
    const body = await res.json();
    expect(body).toEqual({ release_date: "2026-09-14T10:42:00Z" });
  });

  it("returns null, never a fabricated value, when RELEASE_DATE is unset", async () => {
    delete process.env.RELEASE_DATE;
    const res = GET();
    const body = await res.json();
    expect(body).toEqual({ release_date: null });
  });
});
