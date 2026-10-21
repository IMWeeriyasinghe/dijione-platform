import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Module-independence guard for the On-site UI (docs/onsite/architecture.md):
// no imports from other apps, and every API path goes to this module's own
// API or the shared Platform Core auth/notifications surface.
const SRC = path.resolve(__dirname, "..");
const ALLOWED_API = /^\/api\/(onsite|auth|notifications)(\/|$|\?)/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "__tests__" ? [] : files(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

describe("onsite-web module boundaries", () => {
  const sources = files(SRC).map((f) => ({ f, text: readFileSync(f, "utf8") }));

  it("never imports from another app", () => {
    for (const { f, text } of sources) {
      const imports = [...text.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
      for (const spec of imports) {
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

  it("does not use attendance-policy wording", () => {
    for (const { f, text } of sources) {
      const visible = text.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
      for (const word of [/\bPresent\b/, /\bAbsent\b/, /\bLate\b/, /\bEarly\b/, /Working hours/i, /Currently present/i]) {
        expect(visible, `${f}: ${word}`).not.toMatch(word);
      }
    }
  });
});
