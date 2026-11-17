#!/usr/bin/env node
/**
 * Change-aware CI scoping (docs/platform/engineering-gatekeeper.md §4 and §6).
 *
 *   node scripts/ci/ci-scope.js scope  --workflow <name> --event <event> [--draft true|false]
 *                                       [--changed-files <file> | --diff-unavailable]
 *                                       [--lockfile-base <file> --lockfile-head <file>]
 *   node scripts/ci/ci-scope.js verify
 *
 * `scope` decides which jobs/matrix legs of the CI workflow a pull request
 * must run. The workflow declares its legs inline (the `CI_SCOPE_SPEC` env of
 * its `scope` step), so they stay visible in the workflow file and this
 * script holds no application names — only generic rules.
 *
 * A leg runs when the PR changes `apps/<id>/<within>` (default: anything in
 * the app), a shared dependency of its kind (SHARED below), or a path the
 * leg declares in `also`. A draft PR runs no scoped leg; marking it ready
 * for review re-runs the scope on the whole diff. A scheduled run runs only
 * jobs marked `onSchedule`, in full. One narrowing:
 * a root package-lock.json change whose ONLY difference (merge base vs PR
 * head) is the `version` of `apps/<id>` workspace entries — a per-app
 * release bump — counts as a change to those apps, not to every Node leg.
 *
 * Fail-safe: EVERY leg runs ("full" mode) when
 *   - the event is a push or a manual run (workflow_dispatch);
 *   - the changed-file list is unavailable, empty, or at GitHub's 3000-file
 *     API limit;
 *   - the PR changes this workflow file, the scoping action or this script;
 *   - the PR changes a path no rule knows about (KNOWN_PATHS).
 *
 * `verify` runs in the workflow's `<workflow>-result` job. It fails unless
 * the scope job succeeded, every job that had to run succeeded, and every
 * job that was scoped out was skipped (never failed or cancelled).
 *
 * Node built-ins only; no dependencies.
 */

const fs = require("node:fs");

// GitHub's "list pull request files" API stops at 3000 files.
const MAX_PR_FILES = 3000;

// Shared inputs by leg kind. A change here fans out to every leg of that kind.
const SHARED = {
  python: [
    "packages/auth-client-py/**",
    "packages/mail-client-py/**",
    ".python-version",
  ],
  node: [
    "packages/design-system/**",
    "packages/auth-client-ts/**",
    "packages/contracts/**",
    "package.json",
    "package-lock.json",
    ".nvmrc",
  ],
};

// Changing these re-runs every leg of every workflow.
const FULL_RUN_PATHS = [".github/actions/**", "scripts/ci/**", ".gitattributes"];

// Paths a rule knows about. A changed path outside these (and outside
// SHARED) is unknown, and an unknown path forces a full run.
const KNOWN_PATHS = [
  "apps/**",
  "packages/README.md",
  "deploy/**",
  "docs/**",
  "scripts/**",
  ".github/**",
  ".claude/**",
  "agents/**",
  "modules/**",
  "integrations/**",
  "*.md",
  ".dockerignore",
  ".editorconfig",
  ".env.example",
  ".gitignore",
  ".pre-commit-config.yaml",
];

const MATRIX_ID_KEYS = ["service", "app"];

const LOCKFILE = "package-lock.json";
const WORKSPACE_APP = /^apps\/([^/]+)$/;

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

/**
 * A per-app release bumps `packages["apps/<id>"].version` in the root
 * lockfile. That is a change to that app only, not to the shared dependency
 * tree. Returns the app ids whose workspace version changed when that is the
 * ONLY difference between the two lockfiles; returns null for any other
 * difference or anything unexpected (caller then keeps the full fan-out).
 */
function lockfileVersionOnlyApps(base, head) {
  if (!base || !head || typeof base !== "object" || typeof head !== "object") return null;
  if (!base.packages || !head.packages) return null;
  const strip = (lock) => {
    const packages = {};
    for (const [key, entry] of Object.entries(lock.packages)) {
      if (WORKSPACE_APP.test(key) && entry && typeof entry === "object") {
        const { version, ...rest } = entry;
        packages[key] = rest;
      } else {
        packages[key] = entry;
      }
    }
    return { ...lock, packages };
  };
  if (canonical(strip(base)) !== canonical(strip(head))) return null;
  const apps = [];
  for (const key of Object.keys(head.packages)) {
    const m = key.match(WORKSPACE_APP);
    if (m && base.packages[key] && base.packages[key].version !== head.packages[key].version) apps.push(m[1]);
  }
  return apps;
}

function globToRegExp(glob) {
  let re = "";
  for (let i = 0; i < glob.length; i += 1) {
    const c = glob[i];
    if (c === "*" && glob[i + 1] === "*") {
      if (glob[i + 2] === "/") {
        re += "(?:.*/)?";
        i += 2;
      } else {
        re += ".*";
        i += 1;
      }
    } else if (c === "*") {
      re += "[^/]*";
    } else {
      re += c.replace(/[.+?^${}()|[\]\\]/g, "\\$&");
    }
  }
  return new RegExp(`^${re}$`);
}

const globCache = new Map();
function matches(file, globs) {
  return globs.some((g) => {
    if (!globCache.has(g)) globCache.set(g, globToRegExp(g));
    return globCache.get(g).test(file);
  });
}

function entryId(entry, job) {
  for (const key of MATRIX_ID_KEYS) if (typeof entry[key] === "string") return entry[key];
  throw new Error(`${job}: matrix entry ${JSON.stringify(entry)} has no service/app id`);
}

/**
 * Normalise a workflow spec into units: one per matrix leg, or one per
 * non-matrix job. Each unit knows the paths that select it.
 */
function compileSpec(spec) {
  if (!spec || typeof spec !== "object" || Array.isArray(spec) || !Object.keys(spec).length) {
    throw new Error("spec must be a non-empty object of jobs");
  }
  const jobs = [];
  for (const [job, def] of Object.entries(spec)) {
    const shared = [].concat(def.shared || []);
    for (const kind of shared) {
      if (!SHARED[kind]) throw new Error(`${job}: unknown shared kind "${kind}"`);
    }
    const base = [...shared.flatMap((k) => SHARED[k]), ...(def.also || [])];
    // `within`: app-relative globs that count as a change to the app for this
    // job (default: anything in the app).
    const within = def.within || ["**"];
    if (!Array.isArray(within) || !within.length) throw new Error(`${job}: within must be a non-empty list`);
    const appPaths = (id) => within.map((w) => `apps/${id}/${w}`);
    const onSchedule = def.onSchedule === true;
    if (Array.isArray(def.matrix)) {
      if (!def.matrix.length) throw new Error(`${job}: matrix is empty`);
      const legs = def.matrix.map((entry) => {
        const id = entryId(entry, job);
        const { also = [], ...matrixFields } = entry;
        return { id, matrixFields, paths: [...appPaths(id), ...base, ...also] };
      });
      jobs.push({ job, matrix: true, onSchedule, legs });
    } else if (Array.isArray(def.apps) && def.apps.length) {
      const paths = [...def.apps.flatMap(appPaths), ...base];
      jobs.push({ job, matrix: false, onSchedule, legs: [{ id: job, paths }] });
    } else {
      throw new Error(`${job}: needs a non-empty "matrix" or "apps" list`);
    }
  }
  return jobs;
}

/**
 * @param {{workflow: string, event: string, spec: object,
 *          changedFiles?: string[] | null,
 *          lockfile?: {base: object, head: object} | null}} input
 *   changedFiles null/undefined means the diff could not be read.
 *   lockfile: the root lockfile at the merge base and at the PR head, when
 *   the PR changes it (see lockfileVersionOnlyApps).
 *   draft: the pull request is a draft — no scoped leg runs until it is
 *   marked ready for review (that event re-runs the scope on the full diff).
 */
function computeScope({ workflow, event, spec, changedFiles, lockfile = null, draft = false }) {
  const jobs = compileSpec(spec);
  const fullReasons = [];
  const notes = [];
  const ownWorkflow = [`.github/workflows/${workflow}.yml`, `.github/workflows/${workflow}.yaml`];
  let files = changedFiles == null ? null : [...new Set(changedFiles.map((f) => f.trim()).filter(Boolean))];

  if (files && files.includes(LOCKFILE)) {
    const apps = lockfile ? lockfileVersionOnlyApps(lockfile.base, lockfile.head) : null;
    if (apps) {
      files = [...files.filter((f) => f !== LOCKFILE), ...apps.map((a) => `apps/${a}/${LOCKFILE}`)];
      notes.push(`${LOCKFILE}: only workspace versions changed (${apps.join(", ") || "none"}) — treated as app changes`);
    } else {
      notes.push(`${LOCKFILE}: dependency tree changed (or could not be compared) — every Node leg runs`);
    }
  }

  if (event === "schedule") {
    return finish(jobs, workflow, "schedule",
      ["scheduled run: only jobs marked onSchedule run, in full"], [], new Map());
  }
  if (event === "pull_request" && draft) {
    return finish(jobs, workflow, "draft",
      ["draft pull request: scoped legs run when it is marked ready for review"], [], new Map());
  }
  if (event !== "pull_request") fullReasons.push(`event "${event}" always runs every leg`);
  else if (files == null) fullReasons.push("changed-file list unavailable");
  else if (files.length === 0) fullReasons.push("changed-file list is empty");
  else if (files.length >= MAX_PR_FILES) fullReasons.push(`${files.length} changed files (API limit ${MAX_PR_FILES})`);

  const hits = new Map(); // leg key -> files that selected it
  if (!fullReasons.length) {
    const fullPaths = [];
    const unknown = [];
    for (const file of files) {
      if (matches(file, FULL_RUN_PATHS) || ownWorkflow.includes(file)) {
        fullPaths.push(file);
        continue;
      }
      let selected = false;
      for (const j of jobs) {
        for (const leg of j.legs) {
          if (matches(file, leg.paths)) {
            const key = `${j.job}/${leg.id}`;
            if (!hits.has(key)) hits.set(key, []);
            hits.get(key).push(file);
            selected = true;
          }
        }
      }
      if (!selected && !matches(file, KNOWN_PATHS) && !matches(file, Object.values(SHARED).flat())) {
        unknown.push(file);
      }
    }
    if (fullPaths.length) fullReasons.push(`CI scoping inputs changed: ${fullPaths.join(", ")}`);
    if (unknown.length) fullReasons.push(`paths no rule covers: ${unknown.join(", ")}`);
  }

  const full = fullReasons.length > 0;
  return finish(jobs, workflow, full ? "full" : "scoped", fullReasons, full ? [] : notes, hits);
}

function finish(jobs, workflow, mode, reasons, notes, hits) {
  const result = { workflow, mode, reasons, notes, jobs: {} };
  for (const j of jobs) {
    const legs = j.legs.map((leg) => {
      const why = hits.get(`${j.job}/${leg.id}`) || [];
      const run = mode === "full" || (mode === "schedule" && j.onSchedule) || (mode === "scoped" && why.length > 0);
      return { id: leg.id, run, matrixFields: leg.matrixFields, because: mode === "scoped" ? why : [] };
    });
    const run = legs.some((l) => l.run);
    result.jobs[j.job] = {
      matrix: j.matrix,
      run,
      include: j.matrix ? legs.filter((l) => l.run).map((l) => l.matrixFields) : undefined,
      legs,
    };
  }
  return result;
}

const outputKey = (job) => job.replace(/[^A-Za-z0-9]/g, "_");

function scopeOutputs(result) {
  const out = { mode: result.mode };
  for (const [job, r] of Object.entries(result.jobs)) {
    out[`run_${outputKey(job)}`] = String(r.run);
    if (r.matrix) out[outputKey(job)] = JSON.stringify({ include: r.include });
  }
  return out;
}

function scopeSummary(result) {
  const lines = [`### CI scope — \`${result.workflow}\`: **${result.mode}**`, ""];
  if (result.mode === "full") {
    lines.push("Every leg runs because:", ...result.reasons.map((r) => `- ${r}`), "");
  } else if (result.reasons.length) {
    lines.push(...result.reasons.map((r) => `- ${r}`), "");
  }
  if (result.notes.length) lines.push(...result.notes.map((n) => `- ${n}`), "");
  const skipped = {
    scoped: "skipped — no change to its inputs",
    draft: "skipped — draft PR",
    schedule: "skipped — not a scheduled job",
  }[result.mode];
  lines.push("| Job | Leg | Decision | Changed paths that selected it |", "|---|---|---|---|");
  for (const [job, r] of Object.entries(result.jobs)) {
    for (const leg of r.legs) {
      const decision = leg.run ? "RUN" : skipped;
      const shown = leg.because.slice(0, 3).map((f) => `\`${f}\``).join(", ");
      const more = leg.because.length > 3 ? ` (+${leg.because.length - 3} more)` : "";
      lines.push(`| ${job} | ${leg.id} | ${decision} | ${shown}${more} |`);
    }
  }
  return `${lines.join("\n")}\n`;
}

/**
 * @param {Record<string, {result: string, outputs: Record<string, string>}>} needs
 * @returns {string[]} problems (empty = pass)
 */
function verifyNeeds(needs) {
  const problems = [];
  const scope = needs.scope;
  if (!scope) return ["no `scope` job in needs"];
  if (scope.result !== "success") problems.push(`scope job result is "${scope.result}"`);
  for (const [job, n] of Object.entries(needs)) {
    if (job === "scope") continue;
    const flag = scope.outputs ? scope.outputs[`run_${outputKey(job)}`] : undefined;
    if (flag === undefined) {
      if (n.result !== "success") problems.push(`${job}: always-required job result is "${n.result}"`);
    } else if (flag === "true") {
      if (n.result !== "success") problems.push(`${job}: in scope, result is "${n.result}"`);
    } else if (flag === "false") {
      if (n.result !== "skipped") problems.push(`${job}: scoped out but result is "${n.result}"`);
    } else {
      problems.push(`${job}: unexpected scope flag "${flag}"`);
    }
  }
  return problems;
}

/** Read the inline JSON `CI_SCOPE_SPEC: |` block of a workflow's scope step. */
function readSpecFromWorkflow(text) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((l) => /^\s+CI_SCOPE_SPEC:\s*\|\s*$/.test(l));
  if (start < 0) throw new Error("no `CI_SCOPE_SPEC: |` block found");
  const indent = lines[start].match(/^\s*/)[0].length;
  const body = [];
  for (const line of lines.slice(start + 1)) {
    if (line.trim() && line.match(/^\s*/)[0].length <= indent) break;
    body.push(line);
  }
  return JSON.parse(body.join("\n"));
}

function writeKeyValues(file, values) {
  const text = Object.entries(values).map(([k, v]) => `${k}=${v}\n`).join("");
  if (file) fs.appendFileSync(file, text);
  else process.stdout.write(text);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--diff-unavailable") args.diffUnavailable = true;
    else if (a.startsWith("--")) {
      args[a.slice(2)] = argv[i + 1];
      i += 1;
    } else args._.push(a);
  }
  return args;
}

function main(argv) {
  const args = parseArgs(argv);
  const command = args._[0];
  if (command === "scope") {
    if (!args.workflow || !args.event) throw new Error("scope needs --workflow and --event");
    const spec = JSON.parse(process.env.CI_SCOPE_SPEC || "");
    let changedFiles = null;
    if (!args.diffUnavailable && args["changed-files"]) {
      changedFiles = fs.readFileSync(args["changed-files"], "utf8").split("\n");
    }
    let lockfile = null;
    if (args["lockfile-base"] && args["lockfile-head"]) {
      try {
        lockfile = {
          base: JSON.parse(fs.readFileSync(args["lockfile-base"], "utf8")),
          head: JSON.parse(fs.readFileSync(args["lockfile-head"], "utf8")),
        };
      } catch {
        lockfile = null; // unreadable -> treated as a real dependency change
      }
    }
    const draft = args.draft === "true";
    const result = computeScope({ workflow: args.workflow, event: args.event, spec, changedFiles, lockfile, draft });
    writeKeyValues(process.env.GITHUB_OUTPUT, scopeOutputs(result));
    const summary = scopeSummary(result);
    if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
    process.stdout.write(summary);
    return 0;
  }
  if (command === "verify") {
    const needs = JSON.parse(process.env.NEEDS || "{}");
    const problems = verifyNeeds(needs);
    const report = problems.length
      ? `### Required checks: FAILED\n${problems.map((p) => `- ${p}`).join("\n")}\n`
      : `### Required checks: passed\n${Object.entries(needs).map(([j, n]) => `- ${j}: ${n.result}`).join("\n")}\n`;
    if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, report);
    process.stdout.write(report);
    return problems.length ? 1 : 0;
  }
  throw new Error('usage: ci-scope.js scope|verify (see header)');
}

if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (err) {
    process.stderr.write(`ci-scope: ${err.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = {
  FULL_RUN_PATHS,
  KNOWN_PATHS,
  MAX_PR_FILES,
  SHARED,
  compileSpec,
  computeScope,
  globToRegExp,
  lockfileVersionOnlyApps,
  outputKey,
  readSpecFromWorkflow,
  scopeOutputs,
  scopeSummary,
  verifyNeeds,
};
