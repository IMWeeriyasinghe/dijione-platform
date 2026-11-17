const test = require("node:test");
const assert = require("node:assert/strict");
const { billedMinutes, parseArgs, report, summarize } = require("./actions-usage");

const job = (secs, conclusion = "success") => ({
  conclusion,
  started_at: "2026-11-17T10:00:00Z",
  completed_at: new Date(Date.parse("2026-11-17T10:00:00Z") + secs * 1000).toISOString(),
});

test("each job is billed rounded up to a whole minute; skipped and unfinished jobs cost nothing", () => {
  assert.equal(billedMinutes(job(1)), 1);
  assert.equal(billedMinutes(job(60)), 1);
  assert.equal(billedMinutes(job(61)), 2);
  assert.equal(billedMinutes(job(282)), 5);
  assert.equal(billedMinutes(job(0)), 1);
  assert.equal(billedMinutes(job(30, "skipped")), 0);
  assert.equal(billedMinutes({ conclusion: null, started_at: "2026-11-17T10:00:00Z", completed_at: null }), 0);
  assert.equal(billedMinutes(null), 0);
});

const opts = { since: "2026-11-01", now: new Date("2026-11-16T00:00:00Z"), threshold: 1500, allowance: 2000 };

test("totals, breakdowns and a linear cycle projection", () => {
  const runs = [
    { name: "ci", event: "pull_request", jobs: [job(30), job(90), job(5, "skipped")] },
    { name: "secret-scan", event: "push", jobs: [job(11)] },
  ];
  const s = summarize(runs, opts);
  assert.equal(s.total, 4);
  assert.deepEqual(s.byWorkflow, { ci: 3, "secret-scan": 1 });
  assert.deepEqual(s.byEvent, { pull_request: 3, push: 1 });
  assert.equal(s.projected, 8); // 4 min over 15 days -> 30-day November
  assert.equal(s.status, "OK");
  assert.match(report(s), /CALCULATED from job durations — not official billing/);
});

test("status flips at the early-warning threshold and at the allowance", () => {
  const many = (n) => [{ name: "ci", event: "pull_request", jobs: Array.from({ length: n }, () => job(60)) }];
  assert.equal(summarize(many(1499), opts).status, "OK");
  assert.equal(summarize(many(1500), opts).status, "WARNING");
  assert.equal(summarize(many(2000), opts).status, "OVER ALLOWANCE");
});

test("arguments default to the current month and validate", () => {
  const a = parseArgs([]);
  assert.match(a.since, /^\d{4}-\d{2}-01$/);
  assert.equal(a.threshold, 1500);
  assert.deepEqual(parseArgs(["--since", "2026-11-17", "--threshold", "1200"]).threshold, 1200);
  assert.equal(parseArgs(["--since", "2026-11-17T06:00:00Z"]).since, "2026-11-17T06:00:00Z");
  assert.throws(() => parseArgs(["--since", "17/11/2026"]));
  assert.throws(() => parseArgs(["--budget", "5"]));
});
