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

describe("Phase 4 — real Entra internal auth wiring (IaC)", () => {
  // platform-api's Entra OIDC path (auth_entra.py + core/security.py) is
  // gated on AUTH_MODE=entra + the four ENTRA_* settings. The Bicep must be
  // able to deliver all of them, with the client secret coming from Key
  // Vault (never a param value), and the persona switcher off when entra.
  const mainBicep = read("deploy/bicep/main.bicep");
  const devParams = read("deploy/bicep/main.dev.bicepparam");

  it("main.bicep parameterises authMode with an allowed set and Entra values", () => {
    expect(mainBicep).toMatch(/@allowed\(\s*\[\s*'dev',\s*'entra'\s*\]\s*\)\s*\nparam authMode string/);
    expect(mainBicep).toMatch(/param entraTenantId string/);
    expect(mainBicep).toMatch(/param entraClientId string/);
    expect(mainBicep).toMatch(/param publicBaseUrl string/);
  });

  it("platform-api gets ENTRA_* env only when authMode == entra", () => {
    expect(mainBicep).toMatch(/authMode == 'entra' \? \[\s*\n\s*{ name: 'ENTRA_TENANT_ID'/);
    expect(mainBicep).toMatch(/ENTRA_REDIRECT_URI', value: '\$\{publicBaseUrl\}\/api\/auth\/callback'/);
  });

  it("the Entra client secret is a Key Vault ref, never a param", () => {
    expect(mainBicep).toMatch(/entra-client-secret-\$\{env\}'[\s\S]*envName: 'ENTRA_CLIENT_SECRET'/);
    expect(devParams).not.toMatch(/client.?secret\s*=/i);
  });

  it("DEV enables authMode = entra", () => {
    expect(devParams).toMatch(/param authMode\s*=\s*'entra'/);
  });
});

describe("Phase 4 — controlled read-only provider activation wiring (IaC)", () => {
  // recruitment-api (Lever) and people-api (BambooHR) can each be flipped
  // to a live, read-only provider independently; every other API stays
  // mock. Provider keys come from Key Vault and attach only in live mode.
  const mainBicep = read("deploy/bicep/main.bicep");
  const devParams = read("deploy/bicep/main.dev.bicepparam");

  it("per-service INTEGRATIONS_MODE params exist with mock defaults", () => {
    expect(mainBicep).toMatch(/param recruitmentIntegrationsMode string = 'mock'/);
    expect(mainBicep).toMatch(/param peopleIntegrationsMode string = 'mock'/);
  });

  it("INTEGRATIONS_MODE is no longer a single platform-wide value", () => {
    const commonBlock = mainBicep.match(/var commonApiEnv = \[[^\]]*\]/)?.[0] ?? "";
    expect(commonBlock).not.toMatch(/INTEGRATIONS_MODE/);
    expect(mainBicep).toMatch(/name: 'INTEGRATIONS_MODE', value: recruitmentMode/);
    expect(mainBicep).toMatch(/name: 'INTEGRATIONS_MODE', value: peopleMode/);
  });

  it("provider API keys attach only in live mode, from Key Vault", () => {
    expect(mainBicep).toMatch(/recruitmentMode == 'live'\) \? \[\s*\n\s*{ name: 'lever-api-key-\$\{env\}'/);
    expect(mainBicep).toMatch(/peopleMode == 'live'\) \? \[\s*\n\s*{ name: 'bamboohr-api-key-\$\{env\}'/);
  });

  it("DEV provider modes are one of the allowed values", () => {
    // Phase 4 activated both (KV secrets lever-api-key-dev / bamboohr-api-key-dev
    // are the real gate). The param must still only ever be 'mock' or 'live'.
    expect(devParams).toMatch(/param recruitmentIntegrationsMode\s*=\s*'(mock|live)'/);
    expect(devParams).toMatch(/param peopleIntegrationsMode\s*=\s*'(mock|live)'/);
    // when a provider is live its subdomain/secret contract must hold:
    if (/param peopleIntegrationsMode\s*=\s*'live'/.test(devParams)) {
      expect(devParams).toMatch(/param bamboohrSubdomain\s*=\s*'[a-z0-9-]+'/);
    }
  });
});
