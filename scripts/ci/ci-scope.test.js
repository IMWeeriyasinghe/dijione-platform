const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  MAX_PR_FILES,
  SHARED,
  computeScope,
  globToRegExp,
  lockfileVersionOnlyApps,
  outputKey,
  readSpecFromWorkflow,
  scopeOutputs,
  scopeSummary,
  verifyNeeds,
} = require("./ci-scope");

const REPO_ROOT = path.resolve(__dirname, "../..");
const WORKFLOWS_DIR = path.join(REPO_ROOT, ".github/workflows");
const SCOPED_WORKFLOWS = ["ci"];

// Synthetic spec: generic ids only.
const SPEC = {
  "lint-test": {
    shared: ["python"],
    matrix: [
      { service: "alpha-api" },
      { service: "beta-api", db: "beta_dev" },
      { service: "gamma-api", also: ["apps/gamma-web/fixtures/**"] },
    ],
  },
  "lint-build": {
    shared: ["node"],
    matrix: [{ app: "alpha-web", also: ["deploy/**"] }, { app: "beta-web" }],
  },
  "bundle": { shared: ["node"], apps: ["alpha-web", "beta-web"], also: ["scripts/guard.js"], onSchedule: true },
  "migrate": { shared: ["python"], within: ["alembic/**", "app/models/**"], matrix: [{ service: "alpha-api" }] },
};
const NONE = { "lint-test": [], "lint-build": [], bundle: [], migrate: [] };
const ALL = {
  "lint-test": ["alpha-api", "beta-api", "gamma-api"],
  "lint-build": ["alpha-web", "beta-web"],
  bundle: ["bundle"],
  migrate: ["alpha-api"],
};

const scope = (changedFiles, event = "pull_request", extra = {}) =>
  computeScope({ workflow: "demo", event, spec: SPEC, changedFiles, ...extra });
const running = (r) =>
  Object.fromEntries(Object.entries(r.jobs).map(([j, v]) => [j, v.legs.filter((l) => l.run).map((l) => l.id)]));

test("glob: ** spans directories, * stays within one segment", () => {
  assert.ok(globToRegExp("apps/x/**").test("apps/x/a/b.py"));
  assert.ok(!globToRegExp("apps/x/**").test("apps/xy/a.py"));
  assert.ok(globToRegExp("*.md").test("README.md"));
  assert.ok(!globToRegExp("*.md").test("docs/README.md"));
  assert.ok(globToRegExp("a/**/b").test("a/b") && globToRegExp("a/**/b").test("a/x/y/b"));
  assert.ok(!globToRegExp("package.json").test("packageXjson"));
});

test("push and manual runs always run every leg", () => {
  for (const event of ["push", "workflow_dispatch"]) {
    const r = scope(["docs/a.md"], event);
    assert.equal(r.mode, "full", event);
    assert.deepEqual(running(r), ALL);
  }
});

test("a scheduled run runs only onSchedule jobs, in full", () => {
  const r = scope(null, "schedule");
  assert.equal(r.mode, "schedule");
  assert.deepEqual(running(r), { ...NONE, bundle: ["bundle"] });
  assert.match(scopeSummary(r), /skipped — not a scheduled job/);
});

test("a draft pull request runs no scoped leg, whatever it changes", () => {
  for (const files of [["apps/alpha-api/app/x.py"], ["scripts/ci/ci-scope.js"], ["Makefile"], null]) {
    const r = scope(files, "pull_request", { draft: true });
    assert.equal(r.mode, "draft", JSON.stringify(files));
    assert.deepEqual(running(r), NONE);
    assert.match(scopeSummary(r), /draft pull request/);
  }
  // marking it ready re-runs the scope on the whole diff
  assert.deepEqual(running(scope(["apps/alpha-api/app/x.py"], "pull_request", { draft: false }))["lint-test"], ["alpha-api"]);
});

test("an unreadable, empty or truncated diff runs every leg", () => {
  assert.equal(scope(null).mode, "full");
  assert.equal(scope([]).mode, "full");
  assert.equal(scope(["", "  "]).mode, "full");
  const huge = Array.from({ length: MAX_PR_FILES }, (_, i) => `docs/f${i}.md`);
  assert.equal(scope(huge).mode, "full");
});

test("a docs-only pull request runs no scoped leg", () => {
  const r = scope(["docs/platform/x.md", "README.md", ".claude/settings.json", "docs/a/b/c.png"]);
  assert.equal(r.mode, "scoped");
  assert.deepEqual(running(r), NONE);
  assert.deepEqual(scopeOutputs(r), {
    mode: "scoped",
    run_lint_test: "false",
    lint_test: '{"include":[]}',
    run_lint_build: "false",
    lint_build: '{"include":[]}',
    run_bundle: "false",
    run_migrate: "false",
    migrate: '{"include":[]}',
  });
});

test("an app change runs only that app's legs", () => {
  const r = scope(["apps/beta-api/app/x.py"]);
  assert.equal(r.mode, "scoped");
  assert.deepEqual(running(r), { ...NONE, "lint-test": ["beta-api"] });
  // matrix fields pass through; `also` never leaks into the matrix
  assert.deepEqual(r.jobs["lint-test"].include, [{ service: "beta-api", db: "beta_dev" }]);
});

test("`within` limits which app paths select a job", () => {
  assert.deepEqual(running(scope(["apps/alpha-api/app/routes/x.py"])), { ...NONE, "lint-test": ["alpha-api"] });
  for (const f of ["apps/alpha-api/alembic/versions/1.py", "apps/alpha-api/app/models/user.py"]) {
    assert.deepEqual(running(scope([f])), { ...NONE, "lint-test": ["alpha-api"], migrate: ["alpha-api"] }, f);
  }
});

test("an app's own README still counts as a change to that app", () => {
  assert.deepEqual(running(scope(["apps/alpha-web/README.md"]))["lint-build"], ["alpha-web"]);
});

test("a shared Python input fans out to every Python leg and no Node leg", () => {
  for (const file of ["packages/auth-client-py/x.py", "packages/mail-client-py/y.py", ".python-version"]) {
    assert.deepEqual(running(scope([file])), { ...NONE, "lint-test": ALL["lint-test"], migrate: ["alpha-api"] }, file);
  }
});

test("a shared Node input fans out to every Node leg and no Python leg", () => {
  for (const file of ["package-lock.json", "package.json", ".nvmrc", "packages/design-system/src/a.tsx",
    "packages/contracts/x.ts", "packages/auth-client-ts/y.ts"]) {
    assert.deepEqual(running(scope([file])), { ...NONE, "lint-build": ALL["lint-build"], bundle: ["bundle"] }, file);
  }
});

test("declared cross-directory inputs (`also`) select their leg", () => {
  assert.deepEqual(running(scope(["deploy/bicep/main.bicep"])), { ...NONE, "lint-build": ["alpha-web"] });
  assert.deepEqual(running(scope(["apps/gamma-web/fixtures/a.json"]))["lint-test"], ["gamma-api"]);
  assert.deepEqual(running(scope(["scripts/guard.js"])).bundle, ["bundle"]);
});

test("changes to the scoping machinery or this workflow run every leg", () => {
  for (const file of [".github/actions/ci-scope/action.yml", "scripts/ci/ci-scope.js",
    ".github/workflows/demo.yml", ".github/workflows/demo.yaml", ".gitattributes"]) {
    const r = scope(["docs/a.md", file]);
    assert.equal(r.mode, "full", file);
    assert.match(r.reasons.join(), /CI scoping inputs changed/);
  }
});

test("another workflow's file does not widen this workflow", () => {
  const r = scope([".github/workflows/other.yml"]);
  assert.equal(r.mode, "scoped");
  assert.deepEqual(running(r), NONE);
});

test("an unknown path runs every leg (fail-safe)", () => {
  for (const file of ["Makefile", "tools/new.sh", "packages/new-shared-lib/index.ts", "docker-compose.yml"]) {
    const r = scope(["docs/a.md", file]);
    assert.equal(r.mode, "full", file);
    assert.match(r.reasons.join(), /paths no rule covers/);
  }
});

const lock = (over = {}) => ({
  name: "root",
  lockfileVersion: 3,
  packages: {
    "": { name: "root", workspaces: ["apps/alpha-web", "apps/beta-web"] },
    "apps/alpha-web": { version: "1.0.0", dependencies: { react: "^19" } },
    "apps/beta-web": { version: "2.0.0" },
    "node_modules/react": { version: "19.0.0", resolved: "https://r/react-19.0.0.tgz" },
    ...over,
  },
});

test("lockfile: a workspace version bump is a change to that app only", () => {
  const head = lock({ "apps/alpha-web": { version: "1.0.1", dependencies: { react: "^19" } } });
  const r = scope(["apps/alpha-web/package.json", "package-lock.json"]);
  assert.deepEqual(running(r)["lint-build"], ["alpha-web", "beta-web"], "without lockfile content: fan-out");
  const narrowed = scope(["apps/alpha-web/package.json", "package-lock.json"], "pull_request",
    { lockfile: { base: lock(), head } });
  assert.deepEqual(running(narrowed), { ...NONE, "lint-build": ["alpha-web"], bundle: ["bundle"] });
  assert.match(narrowed.notes.join(), /only workspace versions changed \(alpha-web\)/);
});

test("lockfile: any dependency-tree difference keeps the full Node fan-out", () => {
  const heads = [
    lock({ "node_modules/react": { version: "19.1.0", resolved: "https://r/react-19.1.0.tgz" } }),
    lock({ "apps/alpha-web": { version: "1.0.1", dependencies: { react: "^20" } } }),
    lock({ "apps/gamma-web": { version: "0.1.0" } }),
    { ...lock(), lockfileVersion: 2 },
    { ...lock(), packages: undefined },
  ];
  for (const head of heads) {
    const r = scope(["package-lock.json"], "pull_request", { lockfile: { base: lock(), head } });
    assert.deepEqual(running(r)["lint-build"], ["alpha-web", "beta-web"], JSON.stringify(head).slice(0, 80));
  }
  assert.equal(lockfileVersionOnlyApps(null, lock()), null);
  assert.equal(lockfileVersionOnlyApps(lock(), "x"), null);
});

test("lockfile: identical content selects nothing", () => {
  assert.deepEqual(lockfileVersionOnlyApps(lock(), lock()), []);
});

test("invalid specs are rejected, never silently empty", () => {
  const bad = [{}, [], null, { j: {} }, { j: { matrix: [] } }, { j: { matrix: [{ x: 1 }] } },
    { j: { shared: ["cobol"], apps: ["a"] } }, { j: { apps: ["a"], within: [] } }];
  for (const spec of bad) {
    assert.throws(() => computeScope({ workflow: "w", event: "pull_request", spec, changedFiles: ["a"] }));
  }
});

test("outputKey makes job ids safe output names", () => {
  assert.equal(outputKey("x-removal-api"), "x_removal_api");
});

// verify: the result job's decision.
const ok = (outputs) => ({ result: "success", outputs });
test("verify passes when in-scope jobs succeed and scoped-out jobs are skipped", () => {
  assert.deepEqual(verifyNeeds({
    scope: ok({ run_a: "true", run_b: "false" }),
    a: { result: "success" },
    b: { result: "skipped" },
    guard: { result: "success" },
  }), []);
});

test("verify fails on any failed, cancelled or missing evidence", () => {
  const cases = [
    { scope: { result: "failure", outputs: {} } },
    { scope: ok({ run_a: "true" }), a: { result: "failure" } },
    { scope: ok({ run_a: "true" }), a: { result: "cancelled" } },
    { scope: ok({ run_a: "true" }), a: { result: "skipped" } },
    { scope: ok({ run_a: "false" }), a: { result: "failure" } },
    { scope: ok({ run_a: "false" }), a: { result: "success" } },
    { scope: ok({ run_a: "maybe" }), a: { result: "success" } },
    { scope: ok({}), guard: { result: "failure" } },
    { scope: ok({}), guard: { result: "skipped" } },
    { a: { result: "success" } },
  ];
  for (const needs of cases) assert.notDeepEqual(verifyNeeds(needs), [], JSON.stringify(needs));
});

// The real workflow: wiring that would otherwise let a leg be bypassed.
function topLevelJobs(text) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((l) => l === "jobs:");
  return lines.slice(start + 1).map((l) => l.match(/^ {2}([A-Za-z0-9_-]+):\s*$/)).filter(Boolean).map((m) => m[1]);
}

for (const wf of SCOPED_WORKFLOWS) {
  const file = path.join(WORKFLOWS_DIR, `${wf}.yml`);
  const text = fs.readFileSync(file, "utf8");
  const spec = readSpecFromWorkflow(text);

  test(`${wf}.yml: every scoped job is gated by its own flag and fed its own matrix`, () => {
    for (const job of Object.keys(spec)) {
      const key = outputKey(job);
      assert.ok(text.includes(`run_${key}: \${{ steps.scope.outputs.run_${key} }}`), `${job}: scope output`);
      assert.match(text, new RegExp(`\\n  ${job}:\\n    needs: scope\\n    if: needs\\.scope\\.outputs\\.run_${key} == 'true'\\n`), `${job}: gate`);
      if (Array.isArray(spec[job].matrix)) {
        assert.ok(text.includes(`matrix: \${{ fromJSON(needs.scope.outputs.${key}) }}`), `${job}: matrix`);
        assert.ok(text.includes(`${key}: \${{ steps.scope.outputs.${key} }}`), `${job}: matrix output`);
      }
    }
  });

  test(`${wf}.yml: the result job requires every other job, and only scope-spec jobs are gated`, () => {
    const jobs = topLevelJobs(text);
    const result = `${wf}-result`;
    assert.ok(jobs.includes(result), "result job exists");
    const lines = text.split(/\r?\n/);
    const needsLine = lines[lines.indexOf(`  ${result}:`) + 1];
    const needed = needsLine.replace(/^\s*needs:\s*\[|\]\s*$/g, "").split(",").map((s) => s.trim());
    assert.deepEqual([...needed].sort(), jobs.filter((j) => j !== result).sort());
    assert.ok(text.includes(`  ${result}:\n    needs: [`) && text.includes("if: ${{ !cancelled() }}"));
    // every job except scope, guard and the result job is a scoped job
    assert.deepEqual(jobs.filter((j) => !["scope", "guard", result].includes(j)).sort(), Object.keys(spec).sort());
  });

  test(`${wf}.yml: the scope step is a plain run step in the scope job (not a composite action)`, () => {
    // GitHub forwards only a composite action's DECLARED outputs; the run_*
    // and matrix outputs are named by the spec, so they must be written by a
    // run step whose id is `scope` (PR #122 draft run: outputs were {}).
    const job = text.slice(text.indexOf("\n  scope:\n"), text.indexOf("\n  guard:\n"));
    const step = job.slice(job.indexOf("      - id: scope\n"));
    assert.ok(job.includes("      - id: scope\n"), "step id scope");
    assert.ok(!/\n {8}uses:/.test(step), "scope step must not be a `uses:` action");
    assert.match(step, /\n {8}run: \|\n[\s\S]*node scripts\/ci\/ci-scope\.js "\$\{args\[@\]\}"/);
    assert.match(step, /\n {10}CI_SCOPE_SPEC: \|\n/);
  });

  test(`${wf}.yml: runs on every pull request event, including ready_for_review, with no path filter`, () => {
    const on = text.slice(text.indexOf("\non:\n"), text.indexOf("\nconcurrency:"));
    assert.match(on, /\n {2}pull_request:\n {4}types: \[opened, synchronize, reopened, ready_for_review\]\n/);
    assert.ok(!/paths(-ignore)?:/.test(on), "no paths filter on any trigger");
    assert.match(on, /\n {2}push:\n {4}branches: \[main\]\n/);
    assert.match(on, /\n {2}workflow_dispatch:/);
  });

  test(`${wf}.yml: push runs every leg; the schedule runs exactly the onSchedule jobs`, () => {
    const full = computeScope({ workflow: wf, event: "push", spec, changedFiles: null });
    for (const [job, r] of Object.entries(full.jobs)) {
      assert.ok(r.legs.every((l) => l.run), job);
      if (r.matrix) assert.equal(r.include.length, spec[job].matrix.length, job);
    }
    const weekly = computeScope({ workflow: wf, event: "schedule", spec, changedFiles: null });
    const scheduled = Object.keys(spec).filter((j) => spec[j].onSchedule);
    assert.ok(scheduled.length > 0);
    for (const [job, r] of Object.entries(weekly.jobs)) {
      assert.equal(r.legs.every((l) => l.run), scheduled.includes(job), job);
      assert.equal(r.legs.some((l) => l.run), scheduled.includes(job), job);
    }
  });

  test(`${wf}.yml: each leg is selected by its own app, by its shared kind and by its 'also' paths`, () => {
    for (const [job, def] of Object.entries(spec)) {
      const legs = def.matrix || [{ app: def.apps[0] }];
      const within = (def.within || ["**"])[0];
      for (const leg of legs) {
        const id = leg.service || leg.app;
        const samples = [`apps/${id}/${within}`, ...(leg.also || []), ...(def.also || []),
          ...[].concat(def.shared).map((k) => SHARED[k][0])]
          .map((g) => g.replace(/\*\*/g, "x/y.txt").replace(/\*/g, "z"));
        for (const sample of samples) {
          const r = computeScope({ workflow: wf, event: "pull_request", spec, changedFiles: [sample] });
          const legId = def.matrix ? id : job;
          assert.ok(r.jobs[job].legs.find((l) => l.id === legId).run, `${job}/${legId} <- ${sample}`);
        }
      }
    }
  });

  test(`${wf}.yml: a docs-only pull request runs none of its scoped legs`, () => {
    const r = computeScope({ workflow: wf, event: "pull_request", spec, changedFiles: ["docs/platform/x.md"] });
    assert.equal(r.mode, "scoped");
    for (const v of Object.values(r.jobs)) assert.equal(v.run, false);
  });
}
