const test = require("node:test");
const assert = require("node:assert/strict");
const { ATWORK, classify, findViolations } = require("./check-module-independence");

const run = (files) => findViolations(Object.keys(files), (f) => files[f]);

test("the module's own apps may reference themselves", () => {
  assert.deepEqual(run({
    "apps/onsite-api/app/main.py": "ONSITE_SQL_SERVER = 1",
    "apps/onsite-web/src/lib/api.ts": "fetch('/api/onsite/summary')",
  }), []);
});

test("allow-listed registration points are permitted", () => {
  assert.deepEqual(run({
    "apps/shell-web/next.config.ts": "const ONSITE_WEB_URL = up('ONSITE_WEB_URL')",
    "apps/platform-api/app/core/constants.py": 'MODULE_ONSITE = "onsite"',
    "deploy/bicep/main.bicep": "{ name: 'onsite-api' }",
    "docs/onsite/architecture.md": "onsite-api owns ...",
  }), []);
});

test("zero tolerance in other modules, source domains and shared packages", () => {
  const v = run({
    "apps/birthday-api/app/x.py": "# talks to the onsite module",
    "apps/people-api/app/routes.py": "def on_site(): pass",
    "packages/design-system/src/x.ts": "const OnSite = 1",
  });
  assert.deepEqual(v.map((x) => x.file), [
    "apps/birthday-api/app/x.py", "apps/people-api/app/routes.py", "packages/design-system/src/x.ts",
  ]);
  assert.ok(v.every((x) => x.rule === "zero"));
});

test("runtime references elsewhere are violations", () => {
  const v = run({
    "apps/shell-web/src/app/page.tsx": "fetch('/api/onsite/summary')",
    "apps/platform-api/app/services/x.py": "url = 'http://onsite-api'",
    "scripts/other.js": "process.env.ONSITE_API_URL",
  });
  assert.equal(v.length, 3);
  assert.ok(v.every((x) => x.rule === "guarded"));
});

test("ordinary words are not runtime references in guarded areas", () => {
  assert.deepEqual(run({ "apps/shell-web/src/app/page.tsx": "// on-site meetings" }), []);
});

test("deleted files (module-removal job) are skipped", () => {
  assert.deepEqual(findViolations(["apps/birthday-api/app/gone.py"], () => null), []);
});

test("classify", () => {
  assert.equal(classify("apps/onsite-api/x"), "own");
  assert.equal(classify("apps/talent-api/x"), "zero");
  assert.equal(classify("apps/shell-web/next.config.ts"), "allowed");
  assert.equal(classify("apps/shell-web/src/x.ts"), "guarded");
});

const runAtwork = (files) => findViolations(Object.keys(files), (f) => files[f], ATWORK);

test("DijiAtWork: own apps and registration points are permitted", () => {
  assert.deepEqual(runAtwork({
    "apps/atwork-api/app/main.py": "ATWORK_VALUE = 1",
    "apps/shell-web/next.config.ts": "const ATWORK_WEB_URL = up('ATWORK_WEB_URL')",
    "apps/platform-api/app/core/permissions.py": "ATWORK_ROLES = []",
    "docs/atwork/foundation.md": "atwork-api owns ...",
  }), []);
});

test("DijiAtWork: zero tolerance includes Diji On-site, and the reverse holds", () => {
  const v = runAtwork({
    "apps/onsite-api/app/x.py": "# calls atwork",
    "apps/people-api/app/x.py": "# DijiAtWork field",
    "packages/contracts/src/x.ts": "const dijiAtWork = 1",
  });
  assert.equal(v.length, 3);
  assert.ok(v.every((x) => x.rule === "zero"));
  const reverse = run({ "apps/atwork-api/app/x.py": "# calls onsite", "apps/atwork-web/src/x.ts": "const OnSite = 1" });
  assert.equal(reverse.length, 2);
  assert.ok(reverse.every((x) => x.rule === "zero"));
});

test("DijiAtWork: runtime references elsewhere are violations", () => {
  const v = runAtwork({ "apps/shell-web/src/app/page.tsx": "fetch('/api/atwork/me')", "scripts/other.js": "process.env.ATWORK_API_URL" });
  assert.equal(v.length, 2);
  assert.ok(v.every((x) => x.rule === "guarded"));
});

test("DijiAtWork: the ordinary phrase is not a reference", () => {
  assert.deepEqual(runAtwork({ "packages/design-system/src/x.ts": "// what we do at work, that work" }), []);
});

test("classify per module", () => {
  assert.equal(classify("apps/atwork-api/x", ATWORK), "own");
  assert.equal(classify("apps/onsite-api/x", ATWORK), "zero");
  assert.equal(classify("apps/atwork-api/x"), "zero");
});
