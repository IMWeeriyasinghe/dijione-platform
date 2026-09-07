import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Phase 3 (hosted Azure DEV) regression guards.
 *
 * These lock in two defects found during the hosted DEV end-to-end
 * validation. Both were operational/IaC bugs rather than app-code bugs, so
 * the cheapest durable guard is a static assertion over the deploy assets.
 */

const repoRoot = path.resolve(__dirname, "../../../..");
const read = (rel: string) => readFileSync(path.join(repoRoot, rel), "utf8");

describe("Dockerfile.web bakes the internal proxy URLs at build time (P1)", () => {
  // Next.js evaluates next.config.ts `rewrites()` during `next build` and
  // freezes the resolved upstreams into .next/routes-manifest.json — the
  // standalone server never re-reads process.env for them. The Phase 2
  // images were built with these unset, so `http://localhost:*` fallbacks
  // were baked in and every shell-web `/api/*` and sub-app proxy call in
  // Azure failed with ECONNREFUSED 127.0.0.1. The fix sets the ACA
  // internal-DNS values as build-stage ENV before the build runs.
  const dockerfile = read("deploy/Dockerfile.web");
  const proxyVars = [
    "PLATFORM_API_URL",
    "ADMIN_API_URL",
    "TALENT_API_URL",
    "BIRTHDAY_API_URL",
    "SPARK_API_URL",
    "ADMIN_WEB_URL",
    "TALENT_WEB_URL",
    "BIRTHDAY_WEB_URL",
  ];

  it.each(proxyVars)("declares %s as a build ENV", (name) => {
    expect(dockerfile).toMatch(new RegExp(`ENV[\\s\\S]*${name}=`));
  });

  it("sets the proxy ENV before `npm run build` in the build stage", () => {
    const envIdx = dockerfile.indexOf("PLATFORM_API_URL=${PLATFORM_API_URL}");
    const buildIdx = dockerfile.indexOf("npm run build --workspace");
    expect(envIdx).toBeGreaterThan(-1);
    expect(buildIdx).toBeGreaterThan(-1);
    expect(envIdx).toBeLessThan(buildIdx);
  });

  it("defaults them to the environment-agnostic ACA internal DNS names", () => {
    expect(dockerfile).toMatch(/ARG PLATFORM_API_URL=http:\/\/platform-api\b/);
    expect(dockerfile).toMatch(/ARG TALENT_API_URL=http:\/\/talent-api\b/);
  });
});

describe("DEV identity bootstrap is reproducible from IaC (P0)", () => {
  // The dev personas (dev-login) are seeded by
  // platform-api/scripts/seed.py --identity-only, which is NOT an Alembic
  // migration. On the first hosted bring-up it was never run, so
  // /api/auth/dev-personas returned [] and no one could log in. The fix
  // is a Bicep-declared manual Job, gated on a param that the dev
  // parameter file turns on.
  const mainBicep = read("deploy/bicep/main.bicep");
  const devParams = read("deploy/bicep/main.dev.bicepparam");

  it("main.bicep declares the seedDevIdentities-gated bootstrap job", () => {
    expect(mainBicep).toMatch(/param seedDevIdentities bool/);
    expect(mainBicep).toMatch(/seedDevIdentities/);
    expect(mainBicep).toMatch(/scripts\/seed\.py --identity-only/);
  });

  it("the DEV parameter file enables it", () => {
    expect(devParams).toMatch(/param seedDevIdentities\s*=\s*true/);
  });
});
