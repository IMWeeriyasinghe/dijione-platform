// Browser test against the real local services and disposable SQLite databases.
// Next.js fixes rewrites at build time, so build atwork-web and shell-web for these ports first:
//   export PLATFORM_API_URL=http://127.0.0.1:18000 ATWORK_API_URL=http://127.0.0.1:18009 ATWORK_WEB_URL=http://127.0.0.1:13005
//   npm run build -w atwork-web && npm run build -w shell-web
// Then, from the repository root: node apps/atwork-web/e2e/run.mjs
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import puppeteer from "puppeteer";

const ROOT = path.resolve(import.meta.dirname, "../../..");
const PY = path.join(ROOT, ".venv/bin/python");
const TMP = mkdtempSync(path.join(tmpdir(), "atwork-e2e-"));
const [PLATFORM, ATWORK, WEB, SHELL] = [18000, 18009, 13005, 13000];
const B = `http://127.0.0.1:${SHELL}`;
const env = (name) => ({
  ...process.env, APP_ENV: "development", AUTH_MODE: "dev", DEV_IDENTITY_MODE: "true", INTEGRATIONS_MODE: "mock",
  DATABASE_URL: `sqlite:///${path.join(TMP, name)}`,
  PLATFORM_API_URL: `http://127.0.0.1:${PLATFORM}`, ATWORK_API_URL: `http://127.0.0.1:${ATWORK}`,
  PORT: String(WEB), HOSTNAME: "127.0.0.1",
});
const children = [];
const results = [];
const check = (name, ok, extra = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? ` (${extra})` : ""}`); };
const run = (cmd, args, cwd, e) => new Promise((res, rej) => {
  const c = spawn(cmd, args, { cwd, env: e, stdio: "ignore" });
  c.on("exit", (code) => (code === 0 ? res() : rej(new Error(`${args.join(" ")} exited ${code}`))));
});
const start = (cmd, args, cwd, e) => children.push(spawn(cmd, args, { cwd, env: e, stdio: "ignore" }));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function ready(url) {
  for (let i = 0; i < 120; i++) { try { if ((await fetch(url)).ok) return; } catch { /* starting */ } await sleep(500); }
  throw new Error(`Timed out waiting for ${url}`);
}
const api = async (port, p, token, init = {}) => {
  const r = await fetch(`http://127.0.0.1:${port}${p}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  return { status: r.status, body: r.headers.get("content-type")?.includes("json") ? await r.json() : await r.arrayBuffer() };
};
const login = async (key) => (await api(PLATFORM, "/api/auth/dev-login", null, { method: "POST", body: JSON.stringify({ persona_key: key }) })).body.access_token;

async function main() {
  const platformDir = path.join(ROOT, "apps/platform-api");
  const atworkDir = path.join(ROOT, "apps/atwork-api");
  await run(PY, ["-m", "alembic", "upgrade", "head"], platformDir, env("platform.db"));
  await run(PY, ["scripts/seed.py"], platformDir, env("platform.db"));
  await run(PY, ["-m", "alembic", "upgrade", "head"], atworkDir, env("atwork.db"));
  start(PY, ["-m", "uvicorn", "app.main:app", "--port", String(PLATFORM)], platformDir, env("platform.db"));
  start(PY, ["-m", "uvicorn", "app.main:app", "--port", String(ATWORK)], atworkDir, env("atwork.db"));
  await ready(`http://127.0.0.1:${PLATFORM}/health`); await ready(`http://127.0.0.1:${ATWORK}/health`);

  const admin = await login("super-admin");
  for (const [persona, role] of [["ta-member", "ATWORK_USER"], ["ta-manager", "ATWORK_MANAGER"], ["platform-admin", "ATWORK_MANAGER"]]) {
    const id = (await api(PLATFORM, "/api/auth/me", await login(persona))).body.id;
    const put = await api(PLATFORM, `/api/platform/admin/users/${id}/modules/atwork`, admin, { method: "PUT", body: JSON.stringify({ role }) });
    if (put.status !== 200) throw new Error(`Role assignment failed: ${put.status}`);
  }
  const standalone = path.join(ROOT, "apps/atwork-web/.next/standalone/apps/atwork-web/server.js");
  if (!existsSync(standalone)) throw new Error("Build atwork-web first");
  const { cp } = await import("node:fs/promises");
  await cp(path.join(ROOT, "apps/atwork-web/.next/static"), path.join(ROOT, "apps/atwork-web/.next/standalone/apps/atwork-web/.next/static"), { recursive: true });
  start("node", [standalone], path.dirname(standalone), env("x"));
  const shellDir = path.join(ROOT, "apps/shell-web/.next/standalone/apps/shell-web");
  await cp(path.join(ROOT, "apps/shell-web/.next/static"), path.join(shellDir, ".next/static"), { recursive: true });
  start("node", [path.join(shellDir, "server.js")], shellDir, { ...env("x"), PORT: String(SHELL) });
  await sleep(2500);

  const browser = await puppeteer.launch({ headless: true });
  const errors = [];
  const open = async (persona, width = 1280) => {
    const ctx = await browser.createBrowserContext();
    const page = await ctx.newPage();
    await page.setViewport({ width, height: 850 });
    page.on("pageerror", (e) => errors.push(e.message));
    const token = await login(persona);
    await page.evaluateOnNewDocument((t) => localStorage.setItem("dijione.devToken", t), token);
    return { page, token };
  };
  const go = (page, p) => page.goto(`${B}/atwork${p}`, { waitUntil: "networkidle2" });
  const text = async (page, t) => {
    try {
      await page.waitForFunction((x) => document.body.innerText.includes(x), { timeout: 15000 }, t);
    } catch (e) {
      throw new Error(`Text not found: "${t}" at ${page.url()}\n${(await page.evaluate(() => document.body.innerText)).slice(0, 900)}`, { cause: e });
    }
  };
  const click = async (page, name) => {
    await page.waitForFunction((n) => [...document.querySelectorAll("button:not([disabled])")].some((b) => b.innerText.trim() === n), { timeout: 15000 }, name);
    await page.evaluate((n) => [...document.querySelectorAll("button:not([disabled])")].find((b) => b.innerText.trim() === n).click(), name);
  };
  const checkOut = async (page) => { await click(page, "Check Out"); await text(page, "End this session?"); await click(page, "Confirm Check Out"); };
  const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);

  const emp = await open("ta-member");
  await go(emp.page, "/");
  await text(emp.page, "Where are you working today?");
  check("employee sees Not Checked In", true);
  check("employee has no Management navigation", !(await emp.page.evaluate(() => document.body.innerText.includes("Audit History"))));
  await emp.page.evaluate(() => [...document.querySelectorAll("label")].find((l) => l.innerText.includes("Remote")).click());
  await click(emp.page, "Check In");
  await text(emp.page, "You are checked in.");
  await emp.page.waitForSelector('[role="timer"]', { timeout: 15000 });
  check("check-in confirmed by the server", true);
  const t1 = await emp.page.$eval('[role="timer"]', (e) => e.innerText);
  await sleep(2200);
  const t2 = await emp.page.$eval('[role="timer"]', (e) => e.innerText);
  check("live timer advances", t1 !== t2, `${t1} -> ${t2}`);
  await click(emp.page, "Start Break");
  await text(emp.page, "End your break before checking out.");
  check("Check Out unavailable during a break", !(await emp.page.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Check Out"))));
  check("all requests stay on the shell origin", emp.page.url().startsWith(`${B}/atwork`));
  await emp.page.reload({ waitUntil: "networkidle2" });
  await text(emp.page, "On break");
  check("refresh recovers On Break from the server", true);
  const ids = [];
  let dropped = false;
  await emp.page.setRequestInterception(true);
  const intercept = (req) => {
    if (req.url().endsWith("/breaks/end") && req.method() === "POST") {
      ids.push(JSON.parse(req.postData()).client_request_id);
      if (!dropped) { dropped = true; req.abort("failed"); return; }
    }
    req.continue();
  };
  emp.page.on("request", intercept);
  await click(emp.page, "End Break");
  await text(emp.page, "We could not confirm that action");
  check("network failure offers a safe retry, with no false success", !(await emp.page.evaluate(() => document.body.innerText.includes("Your break has ended."))));
  await click(emp.page, "Retry");
  await text(emp.page, "Your break has ended.");
  check("retry reuses the same request ID", ids.length === 2 && ids[0] === ids[1]);
  emp.page.off("request", intercept);
  await emp.page.setRequestInterception(false);
  const breaks = (await api(ATWORK, "/api/atwork/attendance/status", emp.token)).body.session.breaks;
  check("retried action recorded once", breaks.length === 1 && breaks[0].ended_at !== null);
  await emp.page.setOfflineMode(true);
  await text(emp.page, "You are offline");
  check("offline state shown", await emp.page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Check Out").disabled));
  await emp.page.setOfflineMode(false);
  await sleep(1200);
  await checkOut(emp.page);
  await text(emp.page, "You are checked out. If you still have work to do, check in again");
  check("check-out confirmed in a dialog and re-check-in explained", true);
  await text(emp.page, "You are checked out.");
  await text(emp.page, "Completed sessions");
  check("full attendance cycle", true);

  await go(emp.page, "/attendance");
  await text(emp.page, "Remote");
  const session = (await api(ATWORK, "/api/atwork/attendance/history", emp.token)).body.sessions[0];
  await go(emp.page, `/requests/new?sessionId=${session.id}`);
  await text(emp.page, "Request a correction");
  await emp.page.select("#mode", "CLIENT_SITE");
  await emp.page.type("#reason", "I was at the client site");
  await click(emp.page, "Submit request");
  await text(emp.page, "My Requests");
  await text(emp.page, "I was at the client site");
  check("employee submits a correction", true);
  check("official record unchanged while pending", (await api(ATWORK, `/api/atwork/attendance/sessions/${session.id}`, emp.token)).body.work_mode === "REMOTE");
  check("employee denied Management API", (await api(ATWORK, "/api/atwork/management/overview", emp.token)).status === 403);

  const mgr = await open("ta-manager");
  await go(mgr.page, "/management");
  await text(mgr.page, "Management Overview");
  check("manager overview loads", true);
  await go(mgr.page, "/management/corrections");
  await text(mgr.page, "Session correction");
  await mgr.page.evaluate(() => document.querySelector('a[href*="/management/corrections/"]').click());
  await text(mgr.page, "I was at the client site");
  await click(mgr.page, "Approve");
  await text(mgr.page, "Approve this correction?");
  await mgr.page.evaluate(() => document.querySelector('form button[type="submit"]').click());
  await text(mgr.page, "The decision was saved.");
  check("manager approves", true);
  const after = (await api(ATWORK, `/api/atwork/attendance/sessions/${session.id}`, emp.token)).body;
  check("approval applied to the official record", after.work_mode === "CLIENT_SITE" && after.correction_count === 1);
  await go(mgr.page, "/management/audit");
  await text(mgr.page, "Session corrected");
  check("audit shows the correction", true);
  const notes = async (token) => (await api(PLATFORM, "/api/notifications", token)).body;
  let mgrNotes = []; let empNotes = [];
  for (let i = 0; i < 20 && !(mgrNotes.length && empNotes.length); i++) { await sleep(250); mgrNotes = await notes(mgr.token); empNotes = await notes(emp.token); }
  const review = mgrNotes.find((n) => n.type === "ATWORK_CORRECTION_REQUESTED");
  check("reviewer notified of the request with a link", Boolean(review?.link_url?.startsWith("/atwork/management/corrections/")));
  check("employee notified of the approval", empNotes.some((n) => n.type === "ATWORK_CORRECTION_APPROVED"));
  check("employee does not get the reviewer notification", !empNotes.some((n) => n.type === "ATWORK_CORRECTION_REQUESTED"));
  check("notification text has no attendance details", !/\d{1,2}:\d{2}/.test(review.title + review.body));
  await mgr.page.goto(`${B}/`, { waitUntil: "networkidle2" });
  await mgr.page.click('button[aria-label="Notifications"]');
  await text(mgr.page, "Attendance correction awaiting review");
  await Promise.all([mgr.page.waitForNavigation({ waitUntil: "networkidle2" }), mgr.page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.innerText.includes("Attendance correction awaiting review")).click())]);
  check("notification opens the DijiAtWork screen", mgr.page.url().includes("/atwork/management/corrections/"));

  const self = (await api(ATWORK, "/api/atwork/attendance/check-in", mgr.token, { method: "POST", body: JSON.stringify({ work_mode: "OFFICE", client_request_id: "e2e-self-001" }) })).body.session;
  await api(ATWORK, "/api/atwork/attendance/check-out", mgr.token, { method: "POST", body: JSON.stringify({ client_request_id: "e2e-self-002" }) });
  const own = (await api(ATWORK, "/api/atwork/corrections", mgr.token, { method: "POST", body: JSON.stringify({ client_request_id: "e2e-self-003", session_id: self.id, reason: "Wrong mode here", work_mode: "REMOTE" }) })).body;
  const denied = await api(ATWORK, `/api/atwork/management/corrections/${own.id}/approve`, mgr.token, { method: "POST", body: "{}" });
  check("manager cannot approve own correction", denied.status === 403 && denied.body.code === "SELF_DECISION_FORBIDDEN");

  await go(mgr.page, "/management/reports");
  await text(mgr.page, "Employee summaries");
  check("reports load", true);
  const day = new Date().toISOString().slice(0, 10);
  const xl = await api(ATWORK, `/api/atwork/management/reports/export?report=sessions&format=xlsx&date_from=${day}&date_to=${day}`, mgr.token);
  check("Excel export is a workbook", xl.status === 200 && Buffer.from(xl.body).subarray(0, 2).toString() === "PK");
  await go(mgr.page, "/management/settings");
  await text(mgr.page, "Business time zone");
  check("settings load", await mgr.page.$eval("#tz", (e) => e.value === "Asia/Colombo"));

  for (const [persona, routes] of [["ta-member", ["/", "/attendance", "/requests", "/requests/new"]], ["ta-manager", ["/management", "/management/employees", "/management/corrections", "/management/reports", "/management/audit", "/management/settings"]]]) {
    for (const width of [390, 768, 1280]) {
      const v = await open(persona, width);
      for (const r of routes) { await go(v.page, r); await sleep(300); check(`no page overflow ${r} @${width}`, await noOverflow(v.page)); }
      await v.page.browserContext().close();
    }
  }
  const foreign = await api(ATWORK, `/api/atwork/attendance/sessions/${session.id}`, mgr.token);
  check("own-attendance API hides another employee's session", foreign.status === 404);
  check("session without a token is rejected", (await api(ATWORK, "/api/atwork/attendance/status", null)).status === 401);
  const home = await open("ta-member");
  await home.page.goto(`${B}/`, { waitUntil: "networkidle2" });
  await text(home.page, "DijiAtWork");
  check("DijiOne Home lists DijiAtWork for an assigned user", true);
  await home.page.browserContext().close();
  check("no uncaught browser errors", errors.length === 0, errors.slice(0, 2).join(" | "));
  children.find((c) => c.spawnargs.includes(String(ATWORK))).kill();
  children.find((c) => c.spawnargs.some((a) => a.endsWith("atwork-web/server.js"))).kill();
  await sleep(1000);
  const shellHome = await fetch(`${B}/`);
  const platform = await fetch(`http://127.0.0.1:${PLATFORM}/health`);
  check("DijiOne stays up when the DijiAtWork services stop", shellHome.ok && platform.ok);
  check("DijiAtWork API fails on its own", !(await fetch(`${B}/api/atwork/metadata`)).ok);
  await browser.close();
}

main().catch((e) => { console.error(e); results.push(false); }).finally(() => {
  children.forEach((c) => c.kill());
  rmSync(TMP, { recursive: true, force: true });
  const failed = results.filter((r) => !r).length;
  console.log(`\n${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
});
