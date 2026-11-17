#!/usr/bin/env node
/**
 * Read-only GitHub Actions usage report (docs/platform/ci-operations.md).
 *
 *   node scripts/ci/actions-usage.js [--since YYYY-MM-DD|YYYY-MM-DDTHH:MM:SSZ] [--threshold 1500] [--allowance 2000]
 *
 * Sums the billed minutes of every job that ran since --since (default: the
 * 1st of the current UTC month). GitHub bills each hosted-runner job rounded
 * UP to a whole minute; skipped jobs cost nothing. All jobs here run on
 * ubuntu-latest (1x multiplier).
 *
 * This is a CALCULATION from job timestamps, not GitHub's billing record.
 * The authoritative figure is Settings → Billing and licensing → Usage.
 * Needs the GitHub CLI signed in with read access to the repository; makes
 * GET requests only. Exit code: 0 below the threshold, 3 at/above it.
 */

const { execFile } = require("node:child_process");

function billedMinutes(job) {
  if (!job || job.conclusion === "skipped" || !job.started_at || !job.completed_at) return 0;
  const secs = (Date.parse(job.completed_at) - Date.parse(job.started_at)) / 1000;
  if (!Number.isFinite(secs) || secs < 0) return 0;
  return Math.max(1, Math.ceil(secs / 60));
}

/**
 * @param {{name: string, event: string, jobs: object[]}[]} runs
 * @param {{since: string, now: Date, threshold: number, allowance: number}} opts
 */
function summarize(runs, { since, now, threshold, allowance }) {
  const byWorkflow = {};
  const byEvent = {};
  let total = 0;
  for (const run of runs) {
    const m = run.jobs.reduce((s, j) => s + billedMinutes(j), 0);
    total += m;
    byWorkflow[run.name] = (byWorkflow[run.name] || 0) + m;
    byEvent[run.event] = (byEvent[run.event] || 0) + m;
  }
  const start = Date.parse(since.length === 10 ? `${since}T00:00:00Z` : since);
  const startDate = new Date(start);
  const monthEnd = Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth() + 1, 1);
  const elapsedDays = Math.max(1, (now.getTime() - start) / 86400000);
  const cycleDays = (monthEnd - start) / 86400000;
  const projected = Math.round((total / elapsedDays) * cycleDays);
  const status = total >= allowance ? "OVER ALLOWANCE" : total >= threshold ? "WARNING" : "OK";
  return { since, runs: runs.length, total, byWorkflow, byEvent, projected, threshold, allowance, status };
}

function report(s) {
  const rows = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, v]) => `  ${k.padEnd(24)} ${v}`).join("\n");
  return [
    `GitHub Actions usage since ${s.since} (CALCULATED from job durations — not official billing)`,
    `  runs: ${s.runs}   billed job minutes: ${s.total}`,
    `  linear projection to cycle end: ~${s.projected} (forecast)`,
    `  early-warning threshold: ${s.threshold}   allowance: ${s.allowance}   status: ${s.status}`,
    "by workflow:", rows(s.byWorkflow),
    "by event:", rows(s.byEvent),
    "Authoritative usage: Settings → Billing and licensing → Usage.",
    "",
  ].join("\n");
}

function gh(args) {
  return new Promise((resolve, reject) => {
    execFile("gh", args, { maxBuffer: 64 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) reject(new Error(`gh ${args.join(" ")}: ${stderr || err.message}`));
      else resolve(stdout);
    });
  });
}

async function collect(since) {
  const out = await gh(["api", "--paginate",
    `repos/{owner}/{repo}/actions/runs?created=>=${since}&per_page=100`,
    "--jq", ".workflow_runs[] | [.id, .name, .event] | @tsv"]);
  const runs = out.split("\n").filter(Boolean).map((l) => {
    const [id, name, event] = l.split("\t");
    return { id, name, event, jobs: [] };
  });
  let next = 0;
  const worker = async () => {
    while (next < runs.length) {
      const run = runs[next];
      next += 1;
      const jobs = await gh(["api", "--paginate",
        `repos/{owner}/{repo}/actions/runs/${run.id}/jobs?per_page=100&filter=all`,
        "--jq", ".jobs[] | {conclusion, started_at, completed_at}"]);
      run.jobs = jobs.split("\n").filter(Boolean).map((j) => JSON.parse(j));
    }
  };
  await Promise.all(Array.from({ length: 8 }, worker));
  return runs;
}

function parseArgs(argv) {
  const now = new Date();
  const args = {
    since: `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`,
    threshold: 1500,
    allowance: 2000,
  };
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, "");
    if (!(key in args)) throw new Error(`unknown option ${argv[i]}`);
    args[key] = key === "since" ? argv[i + 1] : Number(argv[i + 1]);
  }
  if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$/.test(args.since)) {
    throw new Error("--since must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ (UTC)");
  }
  return args;
}

if (require.main === module) {
  (async () => {
    const args = parseArgs(process.argv.slice(2));
    const runs = await collect(args.since);
    const s = summarize(runs, { ...args, now: new Date() });
    process.stdout.write(report(s));
    process.exitCode = s.status === "OK" ? 0 : 3;
  })().catch((err) => {
    process.stderr.write(`actions-usage: ${err.message}\n`);
    process.exitCode = 2;
  });
}

module.exports = { billedMinutes, parseArgs, report, summarize };
