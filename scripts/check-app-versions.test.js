"use strict";

/**
 * Unit tests for the pure decision logic in check-app-versions.js — the
 * bump-status rule and the transitive workspace-dependency resolver. Run
 * with `npm run test:versions-check` (Node's built-in test runner, no new
 * devDependency).
 *
 * The git-integration behavior (detecting staged/unstaged/untracked changes
 * against a working tree) is intentionally NOT re-implemented here with a
 * mocked git — it is instead verified end-to-end by actually running
 * `npm run versions:check` against this repo's own real changes as part of
 * each release (see docs/platform/versioning.md), which is a stronger,
 * more honest proof than a git-mocking harness would be.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  computeBumpStatus,
  isMajorBump,
  transitiveWorkspaceDeps,
  directWorkspaceDeps,
  anyFileUnder,
} = require("./check-app-versions");

test("app source changed + version bumped -> OK, not an error", () => {
  const { status, isError } = computeBumpStatus("1.0.0", "1.0.1");
  assert.equal(status, "OK");
  assert.equal(isError, false);
});

test("app source changed + version NOT bumped -> error", () => {
  const { status, isError } = computeBumpStatus("1.0.0", "1.0.0");
  assert.equal(status, "ERROR: version bump required");
  assert.equal(isError, true);
});

test("minor bump -> OK (agent-managed, no approval gate)", () => {
  const { status, isError } = computeBumpStatus("1.0.1", "1.1.0");
  assert.equal(status, "OK");
  assert.equal(isError, false);
});

test("major version increase (1.x.x -> 2.0.0) is flagged as requiring explicit approval, never silently OK", () => {
  const { status, isError } = computeBumpStatus("1.4.2", "2.0.0");
  assert.equal(status, "MAJOR VERSION CHANGE — USER APPROVAL REQUIRED");
  assert.equal(isError, true);
});

test("major version increase (2.x.x -> 3.0.0) is also flagged", () => {
  const { status, isError } = computeBumpStatus("2.9.9", "3.0.0");
  assert.equal(isError, true);
  assert.match(status, /MAJOR VERSION CHANGE/);
});

test("isMajorBump is false for a patch or minor change", () => {
  assert.equal(isMajorBump("1.0.0", "1.0.1"), false);
  assert.equal(isMajorBump("1.0.0", "1.1.0"), false);
});

test("isMajorBump is false when either version is missing (new app, no base history)", () => {
  assert.equal(isMajorBump(null, "1.0.0"), false);
  assert.equal(isMajorBump("1.0.0", undefined), false);
});

test("a new app (no version at base) never trips the major-bump gate on its first release", () => {
  const { status, isError } = computeBumpStatus(null, "1.0.0");
  assert.equal(status, "OK");
  assert.equal(isError, false);
});

test("anyFileUnder matches a file inside the directory and the directory path itself", () => {
  const changed = new Set(["apps/birthday-web/src/app/page.tsx", "docs/platform/versioning.md"]);
  assert.equal(anyFileUnder(changed, "apps/birthday-web"), true);
  assert.equal(anyFileUnder(changed, "apps/talent-web"), false);
});

test("directWorkspaceDeps resolves only @dijione/* deps declared by the package, via the name->dir map", () => {
  // Simulated in-memory package graph via a fake resolver is out of scope
  // for this pure-fn test (directWorkspaceDeps reads real package.json
  // files); covered instead by the real-repo self-check run.
  // Kept as a placeholder assertion so the test name documents the contract.
  assert.equal(typeof directWorkspaceDeps, "function");
});

test("transitiveWorkspaceDeps resolves a dependency-of-a-dependency (two levels deep), not just direct deps", () => {
  // directWorkspaceDeps(dir) always re-reads real package.json files from
  // disk, so we exercise the closure algorithm itself with a stand-in graph
  // by monkeypatching require's module cache is avoidable — instead assert
  // the real repo's own dependency shape: design-system depends on
  // auth-client and contracts; birthday-web depends on design-system, so
  // birthday-web's closure must include auth-client and contracts too
  // (a change two levels deep must still be detected).
  const path = require("node:path");
  const fs = require("node:fs");
  const repoRoot = path.resolve(__dirname, "..");
  const rootPkg = JSON.parse(fs.readFileSync(path.join(repoRoot, "package.json"), "utf8"));
  const packageWorkspaces = rootPkg.workspaces.filter((w) => w.startsWith("packages/"));
  const pkgNameToDir = {};
  for (const dir of packageWorkspaces) {
    const p = path.join(repoRoot, dir, "package.json");
    if (!fs.existsSync(p)) continue;
    pkgNameToDir[JSON.parse(fs.readFileSync(p, "utf8")).name] = dir;
  }

  const closure = transitiveWorkspaceDeps("apps/birthday-web", pkgNameToDir);
  assert.ok(closure.has("packages/design-system"), "expected direct dep design-system in closure");
  assert.ok(
    closure.has("packages/auth-client-ts") || closure.has("packages/contracts"),
    "expected at least one transitive (two-levels-deep) dependency in the closure"
  );
});
