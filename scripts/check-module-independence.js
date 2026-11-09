#!/usr/bin/env node
/**
 * Module-independence guard (docs/onsite/module-removal.md,
 * docs/atwork/module-removal.md — a required acceptance gate).
 *
 *   node scripts/check-module-independence.js
 *
 * Fails when any git-tracked file references a guarded module outside its
 * own apps and the allow-listed,
 * data/config-only registration points. Zero tolerance in the other
 * application modules, the shared source domains and the shared packages:
 * not even the module's name may appear there.
 */

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");

// Other application modules, shared source domains, shared packages.
const SHARED_ZERO_TOLERANCE_PREFIXES = [
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

// Data/config-only registration points — inert when a module is absent.
const SHARED_ALLOWED_PREFIXES = ["docs/", "deploy/", ".github/workflows/"];
const SHARED_ALLOWED_FILES = [
  "package.json",
  "package-lock.json",
  "scripts/dev-all.js",
  "scripts/check-module-independence.js",
  "scripts/check-module-independence.test.js",
  // Gateway routing + Home-card runtime-status path (shell-web).
  "apps/shell-web/next.config.ts",
  "apps/shell-web/src/proxy.ts",
  "apps/shell-web/src/__tests__/proxy.test.ts",
  "apps/shell-web/src/components/home/ModuleCard.tsx",
  // Platform Core registration data (catalog + module registry row).
  "apps/platform-api/app/core/constants.py",
  "apps/platform-api/app/core/permissions.py",
  "apps/platform-api/scripts/seed.py",
];

const ONSITE_OWN = ["apps/onsite-api/", "apps/onsite-web/"];
const ATWORK_OWN = ["apps/atwork-api/", "apps/atwork-web/"];

// Runtime references to a module: its services, env vars, API prefix,
// database, frontend module constant.
const ONSITE_TOKEN = /onsite-api|onsite-web|ONSITE_|\/api\/onsite|onsite_(?:dev|uat|prod|<env>|\$\{)|MODULE_ONSITE|apps\/onsite/;
// Anywhere in a zero-tolerance area.
const ANY_ONSITE = /on[-_ ]?site/i;
const ATWORK_TOKEN = /atwork-api|atwork-web|ATWORK_|\/api\/atwork|atwork_(?:dev|uat|prod|<env>|\$\{)|MODULE_ATWORK|apps\/atwork/;
// Not a bare "at work": that phrase is ordinary English in comments.
const ANY_ATWORK = /\batwork|diji[-_ ]?at[-_ ]?work/i;

const ONSITE = {
  name: "Diji On-site",
  ownPrefixes: ONSITE_OWN,
  token: ONSITE_TOKEN,
  any: ANY_ONSITE,
  zeroPrefixes: [...SHARED_ZERO_TOLERANCE_PREFIXES, ...ATWORK_OWN],
  allowedFiles: new Set([
    ...SHARED_ALLOWED_FILES,
    "apps/platform-api/alembic/versions/i9j0k1l2m3n4_register_onsite_module.py",
    "apps/platform-api/tests/test_onsite_registration.py",
  ]),
};

const ATWORK = {
  name: "DijiAtWork",
  ownPrefixes: ATWORK_OWN,
  token: ATWORK_TOKEN,
  any: ANY_ATWORK,
  zeroPrefixes: [...SHARED_ZERO_TOLERANCE_PREFIXES, ...ONSITE_OWN],
  allowedFiles: new Set([
    ...SHARED_ALLOWED_FILES,
    "apps/platform-api/alembic/versions/atw1reg0b2c3_register_atwork_module.py",
    "apps/platform-api/alembic/versions/atw2att0c3d4_attendance_self_permissions.py",
    "apps/platform-api/alembic/versions/atw3perm1d4e5_atwork_v1_permissions.py",
    "apps/platform-api/tests/test_atwork_registration.py",
  ]),
};

const MODULES = [ONSITE, ATWORK];

const BINARY = /\.(png|jpe?g|gif|ico|webp|woff2?|ttf|eot|pdf|pptx|db|zip)$/i;

function classify(file, module = ONSITE) {
  if (module.ownPrefixes.some((p) => file.startsWith(p))) return "own";
  if (module.zeroPrefixes.some((p) => file.startsWith(p))) return "zero";
  if (module.allowedFiles.has(file) || SHARED_ALLOWED_PREFIXES.some((p) => file.startsWith(p))) return "allowed";
  return "guarded";
}

/** @returns {{file: string, line: number, text: string, rule: string}[]} */
function findViolations(files, readFile, module = ONSITE) {
  const violations = [];
  for (const file of files) {
    const kind = classify(file, module);
    if (kind === "own" || kind === "allowed" || BINARY.test(file)) continue;
    const pattern = kind === "zero" ? module.any : module.token;
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
  const files = trackedFiles();
  let failed = false;
  for (const module of MODULES) {
    const violations = findViolations(files, readRepoFile, module);
    if (violations.length === 0) {
      console.log(`module independence: OK — no ${module.name} references outside its module and registration points`);
      continue;
    }
    failed = true;
    console.error(`module independence: ${module.name}: ${violations.length} violation(s)`);
    for (const v of violations) {
      console.error(`  [${v.rule}] ${v.file}:${v.line}  ${v.text}`);
    }
  }
  return failed ? 1 : 0;
}

module.exports = { classify, findViolations, MODULES, ONSITE, ATWORK, ONSITE_TOKEN, ANY_ONSITE, ATWORK_TOKEN, ANY_ATWORK };

if (require.main === module) {
  process.exit(main());
}
