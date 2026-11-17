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
  verifyNeeds,
} = require("./ci-scope");

const REPO_ROOT = path.resolve(__dirname, "../..");
const WORKFLOWS_DIR = path.join(REPO_ROOT, ".github/workflows");
const SCOPED_WORKFLOWS = ["api", "web", "migrations", "postgres", "module-boundaries"];

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
  "bundle": { shared: ["node"], apps: ["alpha-web", "beta-web"], also: ["scripts/guard.js"] },
};

const scope = (changedFiles, event = "pull_request") =>
  computeScope({ workflow: "demo", event, spec: SPEC, changedFiles });
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

test("non-pull_request events always run every leg", () => {
  for (const event of ["push", "schedule", "workflow_dispatch"]) {
    const r = scope(["docs/a.md"], event);
    assert.equal(r.mode, "full", event);
    assert.deepEqual(running(r), {
      "lint-test": ["alpha-api", "beta-api", "gamma-api"],
      "lint-build": ["alpha-web", "beta-web"],
      bundle: ["bundle"],
    });
  }
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
  assert.deepEqual(running(r), { "lint-test": [], "lint-build": [], bundle: [] });
  assert.deepEqual(scopeOutputs(r), {
    mode: "scoped",
    run_lint_test: "false",
    lint_test: '{"include":[]}',
    run_lint_build: "false",
    lint_build: '{"include":[]}',
    run_bundle: "false",
  });
});

test("an app change runs only that app's legs", () => {
  const r = scope(["apps/beta-api/app/x.py"]);
  assert.equal(r.mode, "scoped");
  assert.deepEqual(running(r), { "lint-test": ["beta-api"], "lint-build": [], bundle: [] });
  // matrix fields pass through; `also` never leaks into the matrix
  assert.deepEqual(r.jobs["lint-test"].include, [{ service: "beta-api", db: "beta_dev" }]);
});

test("an app's own README still counts as a change to that app", () => {
  assert.deepEqual(running(scope(["apps/alpha-web/README.md"]))["lint-build"], ["alpha-web"]);
});

test("a shared Python input fans out to every Python leg and no Node leg", () => {
  for (const file of ["packages/auth-client-py/x.py", "packages/mail-client-py/y.py", ".python-version"]) {
    assert.deepEqual(running(scope([file])), {
      "lint-test": ["alpha-api", "beta-api", "gamma-api"],
      "lint-build": [],
      bundle: [],
    }, file);
  }
});

test("a shared Node input fans out to every Node leg and no Python leg", () => {
  for (const file of ["package-lock.json", "package.json", ".nvmrc", "packages/design-system/src/a.tsx",
    "packages/contracts/x.ts", "packages/auth-client-ts/y.ts"]) {
    assert.deepEqual(running(scope([file])), {
      "lint-test": [],
      "lint-build": ["alpha-web", "beta-web"],
      bundle: ["bundle"],
    }, file);
  }
});

test("declared cross-directory inputs (`also`) select their leg", () => {
  assert.deepEqual(running(scope(["deploy/bicep/main.bicep"])), {
    "lint-test": [],
    "lint-build": ["alpha-web"],
    bundle: [],
  });
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
  assert.deepEqual(running(r), { "lint-test": [], "lint-build": [], bundle: [] });
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
  const narrowed = computeScope({ workflow: "demo", event: "pull_request", spec: SPEC,
    changedFiles: ["apps/alpha-web/package.json", "package-lock.json"], lockfile: { base: lock(), head } });
  assert.deepEqual(running(narrowed), { "lint-test": [], "lint-build": ["alpha-web"], bundle: ["bundle"] });
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
    const r = computeScope({ workflow: "demo", event: "pull_request", spec: SPEC,
      changedFiles: ["package-lock.json"], lockfile: { base: lock(), head } });
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
    { j: { shared: ["cobol"], apps: ["a"] } }];
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

// The real workflows: wiring that would otherwise let a leg be bypassed.
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

  test(`${wf}.yml: the result job requires every other job`, () => {
    const jobs = topLevelJobs(text);
    const result = `${wf}-result`;
    assert.ok(jobs.includes(result), "result job exists");
    const needsLine = text.split(/\r?\n/)[text.split(/\r?\n/).indexOf(`  ${result}:`) + 1];
    const needed = needsLine.replace(/^\s*needs:\s*\[|\]\s*$/g, "").split(",").map((s) => s.trim());
    assert.deepEqual([...needed].sort(), jobs.filter((j) => j !== result).sort());
    assert.ok(text.includes(`  ${result}:\n    needs: [`) && text.includes("if: ${{ !cancelled() }}"));
  });

  test(`${wf}.yml: scope changes trigger the workflow, and push runs every leg`, () => {
    if (wf !== "module-boundaries") {
      assert.ok(text.includes('- ".github/actions/ci-scope/**"') && text.includes('- "scripts/ci/**"'));
    }
    const full = computeScope({ workflow: wf, event: "push", spec, changedFiles: null });
    for (const [job, r] of Object.entries(full.jobs)) {
      assert.ok(r.legs.every((l) => l.run), job);
      if (r.matrix) assert.equal(r.include.length, spec[job].matrix.length, job);
    }
  });

  test(`${wf}.yml: each leg is selected by its own app, by its shared kind and by its 'also' paths`, () => {
    for (const [job, def] of Object.entries(spec)) {
      const legs = def.matrix || [{ id: job, also: [], app: def.apps[0] }];
      for (const leg of legs) {
        const id = leg.service || leg.app;
        const samples = [`apps/${id}/x/y.txt`, ...(leg.also || []), ...(def.also || []),
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
