import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Module independence: no imports from other apps, and every API path goes to
// this module's own API or the shared Platform Core auth/notifications surface.
const SRC = path.resolve(__dirname, "..");
const ALLOWED_API = /^\/api\/(atwork|auth|notifications)(\/|$|\?)/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "__tests__" ? [] : files(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe("atwork-web module boundaries", () => {
  const sources = files(SRC).map((f) => ({ f, text: readFileSync(f, "utf8") }));

  it("never imports from another app", () => {
    for (const { f, text } of sources) {
      for (const [, spec] of text.matchAll(/from\s+["']([^"']+)["']/g)) {
        expect(spec, f).not.toMatch(/(^|\/)apps\//);
        expect(spec, f).not.toMatch(/^\.\.\/\.\.\/\.\.\//);
        if (spec.startsWith("@dijione/")) {
          expect(["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"], f).toContain(spec);
        }
      }
    }
  });

  it("only calls its own API and the shared auth/notification surface", () => {
    for (const { f, text } of sources) {
      for (const m of text.matchAll(/["'`](\/api\/[^"'`$]*)/g)) {
        expect(m[1], f).toMatch(ALLOWED_API);
      }
    }
  });
});
