#!/usr/bin/env node
/**
 * Module-independence guard for Diji On-site (docs/onsite/module-removal.md,
 * architecture rule 7 — a required acceptance gate).
 *
 *   node scripts/check-module-independence.js
 *
 * Fails when any git-tracked file references the On-site module outside its
 * own apps (apps/onsite-api, apps/onsite-web) and the allow-listed,
 * data/config-only registration points. Zero tolerance in the other
 * application modules, the shared source domains and the shared packages:
 * not even the word "onsite" may appear there.
 */

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");

// Runtime references to the module: its services, env vars, API prefix,
// database, frontend module constant.
const ONSITE_TOKEN = /onsite-api|onsite-web|ONSITE_|\/api\/onsite|onsite_(?:dev|uat|prod|<env>|\$\{)|MODULE_ONSITE|apps\/onsite/;
// Anywhere in a zero-tolerance area.
const ANY_ONSITE = /on[-_ ]?site/i;

// The module itself.
const OWN_PREFIXES = ["apps/onsite-api/", "apps/onsite-web/"];

// Data/config-only registration points — inert when On-site is absent.
const ALLOWED_PREFIXES = ["docs/", "deploy/", ".github/workflows/"];
const ALLOWED_FILES = new Set([
  "package.json",
  "package-lock.json",
  "scripts/dev-all.js",
  "scripts/check-module-independence.js",
  "scripts/check-module-independence.test.js",
  // Gateway routing + Home-card runtime-status path (shell-web).
  "apps/shell-web/next.config.ts",
  "apps/shell-web/src/components/home/ModuleCard.tsx",
  // Platform Core registration data (catalog + module registry row).
  "apps/platform-api/app/core/constants.py",
  "apps/platform-api/app/core/permissions.py",
  "apps/platform-api/scripts/seed.py",
  "apps/platform-api/alembic/versions/i9j0k1l2m3n4_register_onsite_module.py",
  "apps/platform-api/tests/test_onsite_registration.py",
]);

// Other application modules, shared source domains, shared packages.
const ZERO_TOLERANCE_PREFIXES = [
  "apps/people-api/",
  "apps/recruitment-api/",
  "apps/commercial-api/",
  "apps/talent-api/",
  "apps/talent-web/",
  "apps/talentflow-portal-web/",
  "apps/birthday-api/",
  "apps/birthday-web/",
  "apps/birthday-supplier-web/",
  "apps/admin-api/",
  "apps/admin-web/",
  "apps/spark-api/",
  "packages/",
];

const BINARY = /\.(png|jpe?g|gif|ico|webp|woff2?|ttf|eot|pdf|pptx|db|zip)$/i;

function classify(file) {
  if (OWN_PREFIXES.some((p) => file.startsWith(p))) return "own";
  if (ZERO_TOLERANCE_PREFIXES.some((p) => file.startsWith(p))) return "zero";
  if (ALLOWED_FILES.has(file) || ALLOWED_PREFIXES.some((p) => file.startsWith(p))) return "allowed";
  return "guarded";
}

/** @returns {{file: string, line: number, text: string, rule: string}[]} */
function findViolations(files, readFile) {
  const violations = [];
  for (const file of files) {
    const kind = classify(file);
    if (kind === "own" || kind === "allowed" || BINARY.test(file)) continue;
    const pattern = kind === "zero" ? ANY_ONSITE : ONSITE_TOKEN;
    const content = readFile(file);
    if (content == null) continue;
    content.split(/\r?\n/).forEach((text, i) => {
      if (pattern.test(text)) {
        violations.push({ file, line: i + 1, text: text.trim().slice(0, 160), rule: kind });
      }
    });
  }
  return violations;
}

function trackedFiles() {
  return execFileSync("git", ["ls-files"], { cwd: REPO_ROOT, encoding: "utf8" })
    .split("\n")
    .filter(Boolean);
}

function readRepoFile(file) {
  try {
    return fs.readFileSync(path.join(REPO_ROOT, file), "utf8");
  } catch {
    return null; // deleted in the working tree (e.g. the module-removal job)
  }
}

function main() {
  const violations = findViolations(trackedFiles(), readRepoFile);
  if (violations.length === 0) {
    console.log("module independence: OK — no Diji On-site references outside its module and registration points");
    return 0;
  }
  console.error(`module independence: ${violations.length} violation(s)`);
  for (const v of violations) {
    console.error(`  [${v.rule}] ${v.file}:${v.line}  ${v.text}`);
  }
  return 1;
}

module.exports = { classify, findViolations, ONSITE_TOKEN, ANY_ONSITE };

if (require.main === module) {
  process.exit(main());
}
