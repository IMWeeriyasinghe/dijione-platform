#!/usr/bin/env node
/**
 * npm run versions:check [-- --base <ref>] [--committed]
 *
 * Answers: "did every DijiOne app whose released artifact actually changes
 * get its own version bumped?" — the artifact-based rule in
 * docs/platform/versioning.md. Reports only; never bumps anything itself,
 * never decides patch vs. minor, and never auto-approves a major bump.
 *
 * DEFAULT MODE compares <base> (default HEAD~1) against the CURRENT WORKING
 * TREE — committed history since <base>, plus staged, unstaged, and
 * untracked changes — because this is meant to run BEFORE the release
 * commit exists, not only after. `--committed` restricts detection to
 * <base>..HEAD only (no working-tree changes), for a CI context that only
 * cares about already-committed history.
 *
 * A changed app is one whose own `apps/<name>/` directory has a diff, OR
 * whose declared @dijione/* workspace-package dependencies (resolved
 * transitively — a change two levels deep in a dependency-of-a-dependency
 * still counts) have a diff. The app's *current* version is always read
 * from the filesystem (so working-tree edits to package.json are seen);
 * its *base* version is read via `git show <base>:...` (the committed
 * state at that ref).
 */
"use strict";

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..");

function git(args) {
  return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" });
}

function parseArgs(argv) {
  let base = "HEAD~1";
  let committed = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--base") base = argv[++i];
    else if (argv[i] === "--committed") committed = true;
  }
  return { base, committed };
}

/** Union of every changed-file source relevant to "what am I about to
 * release", deduplicated. `committed: true` restricts to the first set only. */
function collectChangedFiles(base, committed) {
  const sources = [() => git(["diff", "--name-only", base, "HEAD"])];
  if (!committed) {
    sources.push(
      () => git(["diff", "--name-only"]), // unstaged
      () => git(["diff", "--cached", "--name-only"]), // staged
      () => git(["ls-files", "--others", "--exclude-standard"]) // untracked
    );
  }
  const files = new Set();
  for (const run of sources) {
    let out;
    try {
      out = run();
    } catch {
      continue; // e.g. base ref doesn't resolve (a brand-new repo) — treat as no history to diff
    }
    for (const line of out.split("\n")) {
      const f = line.trim();
      if (f) files.add(f);
    }
  }
  return files;
}

function readJson(absPath) {
  return JSON.parse(fs.readFileSync(absPath, "utf8"));
}

/** The app's version as committed at <base>, or null if the file didn't
 * exist there (a brand-new app). */
function versionAtBase(base, relPath) {
  try {
    return JSON.parse(git(["show", `${base}:${relPath}`])).version;
  } catch {
    return null;
  }
}

function resolvePackageNameToDir(packageWorkspaces) {
  const map = {};
  for (const dir of packageWorkspaces) {
    const p = path.join(REPO_ROOT, dir, "package.json");
    if (!fs.existsSync(p)) continue;
    map[readJson(p).name] = dir;
  }
  return map;
}

/** Direct @dijione/* workspace deps of the package/app at `dir`. */
function directWorkspaceDeps(dir, pkgNameToDir) {
  const p = path.join(REPO_ROOT, dir, "package.json");
  if (!fs.existsSync(p)) return [];
  const pkg = readJson(p);
  const deps = { ...(pkg.dependencies || {}), ...(pkg.peerDependencies || {}) };
  return Object.keys(deps)
    .filter((name) => name.startsWith("@dijione/"))
    .map((name) => pkgNameToDir[name])
    .filter(Boolean);
}

/** Transitive closure of workspace-package dependencies starting at `dir`
 * (excludes `dir` itself). A change anywhere in this closure counts as
 * affecting `dir`'s consumer — covers a dependency-of-a-dependency, not
 * just direct deps. */
function transitiveWorkspaceDeps(dir, pkgNameToDir, seen = new Set()) {
  for (const dep of directWorkspaceDeps(dir, pkgNameToDir)) {
    if (!seen.has(dep)) {
      seen.add(dep);
      transitiveWorkspaceDeps(dep, pkgNameToDir, seen);
    }
  }
  return seen;
}

function anyFileUnder(changedFiles, dir) {
  const prefix = dir.endsWith("/") ? dir : `${dir}/`;
  for (const f of changedFiles) {
    if (f === dir || f.startsWith(prefix)) return true;
  }
  return false;
}

/** major(oldV) < major(newV) => a real major bump occurred. Returns false
 * (not a major bump) if either version is missing/unparseable — the bump
 * check itself still runs independently. */
function isMajorBump(oldVersion, newVersion) {
  if (!oldVersion || !newVersion) return false;
  const oldMajor = parseInt(String(oldVersion).split(".")[0], 10);
  const newMajor = parseInt(String(newVersion).split(".")[0], 10);
  if (Number.isNaN(oldMajor) || Number.isNaN(newMajor)) return false;
  return newMajor > oldMajor;
}

/** The single piece of release-gating policy logic: given an app's version
 * at <base> and its current (working-tree) version, decide the status line
 * and whether this should fail the check. Pure function — no git, no fs —
 * so it's the part covered directly by unit tests. */
function computeBumpStatus(baseVersion, currentVersion) {
  if (baseVersion === currentVersion) {
    return { status: "ERROR: version bump required", isError: true };
  }
  if (isMajorBump(baseVersion, currentVersion)) {
    // A major bump is never silently "OK" — it must be visibly flagged so a
    // human confirms it was the explicitly-approved major bump and not an
    // accident. The script does not approve/reject it; it only refuses to
    // treat it as routine.
    return { status: "MAJOR VERSION CHANGE — USER APPROVAL REQUIRED", isError: true };
  }
  return { status: "OK", isError: false };
}

function pad(s, n) {
  return s.length >= n ? s : s + " ".repeat(n - s.length);
}

function run(argv) {
  const { base, committed } = parseArgs(argv);
  const rootPkg = readJson(path.join(REPO_ROOT, "package.json"));
  const workspaces = rootPkg.workspaces || [];
  const appWorkspaces = workspaces.filter((w) => w.startsWith("apps/"));
  const packageWorkspaces = workspaces.filter((w) => w.startsWith("packages/"));
  const pkgNameToDir = resolvePackageNameToDir(packageWorkspaces);
  const changedFiles = collectChangedFiles(base, committed);

  const results = appWorkspaces.map((appDir) => {
    const appName = appDir.replace(/^apps\//, "");
    const currentVersion = readJson(path.join(REPO_ROOT, appDir, "package.json")).version;
    const baseVersion = versionAtBase(base, `${appDir}/package.json`);

    let isChanged = anyFileUnder(changedFiles, appDir);
    let changedVia = isChanged ? "app source" : null;
    if (!isChanged) {
      const closure = transitiveWorkspaceDeps(appDir, pkgNameToDir);
      for (const depDir of closure) {
        if (anyFileUnder(changedFiles, depDir)) {
          isChanged = true;
          changedVia = `shared package (${depDir})`;
          break;
        }
      }
    }

    return { appName, isChanged, changedVia, baseVersion, currentVersion };
  });

  const changed = results.filter((r) => r.isChanged);
  const untouched = results.filter((r) => !r.isChanged);
  let hasError = false;

  console.log(`Comparing base ${base} -> ${committed ? "HEAD" : "current working tree"}\n`);
  console.log("Changed application artifacts:");
  if (changed.length === 0) console.log("  (none)");
  for (const r of changed) {
    const { status, isError } = computeBumpStatus(r.baseVersion, r.currentVersion);
    if (isError) hasError = true;
    console.log(
      `  ${pad(r.appName, 26)} ${r.baseVersion ?? "(new)"} -> ${r.currentVersion}   ${status}` +
        (r.changedVia && r.changedVia !== "app source" ? `   [via ${r.changedVia}]` : "")
    );
  }

  console.log("\nUntouched:");
  if (untouched.length === 0) console.log("  (none)");
  for (const r of untouched) {
    console.log(`  ${pad(r.appName, 26)} ${r.currentVersion} (unchanged)`);
  }

  if (hasError) {
    console.log(
      "\nOne or more changed apps need attention above: either the version wasn't bumped, or a " +
        "major bump needs explicit user approval before this release proceeds."
    );
  }

  return hasError ? 1 : 0;
}

if (require.main === module) {
  process.exit(run(process.argv.slice(2)));
}

module.exports = {
  computeBumpStatus,
  isMajorBump,
  transitiveWorkspaceDeps,
  directWorkspaceDeps,
  anyFileUnder,
  resolvePackageNameToDir,
  run,
};
