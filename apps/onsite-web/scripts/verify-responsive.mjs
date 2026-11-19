#!/usr/bin/env node
/**
 * npm run responsive-check   (from apps/onsite-web)
 *
 * Real-browser (Puppeteer, already in node_modules) responsive and
 * end-to-end smoke audit for Diji On-site (apps/onsite-web). For every route
 * and Identity Management tab, at 320/375/768/1024/1280/1440 px it asserts:
 *
 *   1. no whole-page horizontal overflow
 *      (document.documentElement.scrollWidth <= innerWidth);
 *   2. from 1024 px up, no data table scrolls horizontally
 *      ([data-scroll-x] scrollWidth <= clientWidth) — ordinary desktop
 *      workflows never need a sideways scroll;
 *   3. no page-level error state is shown and no browser console error.
 *
 * It also drives the main interactions: the Investigate (code detail) and
 * Map dialogs, the ranked-ID drill-down, a period change and the viewer
 * permission boundary (a viewer sees "Administrator access required").
 * It never confirms a mapping — the Map dialog is opened and closed only.
 *
 * REQUIRES a local stack with SYNTHETIC data only: platform-api (8000,
 * AUTH_MODE=dev), onsite-api (8008, INTEGRATIONS_MODE=mock), people-api
 * (8006) and onsite-web (`npm run dev`, 3004). Mint dev tokens:
 *
 *   curl -s -X POST http://localhost:8000/api/auth/dev-login \
 *     -H "Content-Type: application/json" -d '{"persona_key":"super-admin"}'
 *
 * (the persona needs an ONSITE_ADMIN module assignment; the viewer persona
 * an ONSITE_VIEWER one). Then:
 *
 *   ADMIN_TOKEN=<t> VIEWER_TOKEN=<t> npm run responsive-check -- [--screenshots] [--out <dir>]
 *
 * Not wired into CI (needs a live local stack). Output (JSON + optional
 * PNGs) goes to --out (default: the OS temp dir) — never committed.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer";

// 1093 = a 1366 px laptop at 125 % browser zoom (CSS viewport 1366 / 1.25).
const WIDTHS = [320, 375, 768, 1024, 1093, 1280, 1366, 1440, 1920];
const COLLAPSED_WIDTHS = [1093, 1366, 1440];
const HEIGHT = 900;
const ROUTES = [
  "/", "/today", "/activity", "/activity?view=events", "/employees", "/exceptions", "/admin/access",
  "/admin/identity?tab=overview", "/admin/identity?tab=readiness", "/admin/identity?tab=unmapped",
  "/admin/identity?tab=mappings&status=", "/admin/identity?tab=conflicts", "/admin/identity?tab=import",
  "/admin/health", "/admin/sites",
];

function args(argv) {
  const o = { base: "http://localhost:3004/onsite", screenshots: false, out: path.join(os.tmpdir(), "onsite-responsive-audit") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--base-url") o.base = argv[++i];
    else if (argv[i] === "--screenshots") o.screenshots = true;
    else if (argv[i] === "--out") o.out = argv[++i];
  }
  return o;
}

function measure() {
  const vw = window.innerWidth;
  const tables = [...document.querySelectorAll("[data-scroll-x]")]
    .filter((el) => el.getBoundingClientRect().width > 0 && el.scrollWidth > el.clientWidth + 1)
    .map((el) => ({ caption: el.querySelector("caption")?.textContent ?? "", scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
  const culprits = [];
  if (document.documentElement.scrollWidth > vw + 1) {
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (!r.width || r.right <= vw + 1) continue;
      let n = el.parentElement, inScroller = false;
      while (n && n !== document.body) { const s = getComputedStyle(n); if (s.overflowX === "auto" || s.overflowX === "scroll" || s.overflowX === "hidden") { inScroller = true; break; } n = n.parentElement; }
      if (!inScroller) culprits.push({ tag: el.tagName, cls: String(el.className).slice(0, 80), right: Math.round(r.right), text: (el.textContent || "").trim().slice(0, 40) });
      if (culprits.length >= 6) break;
    }
  }
  return {
    pageOverflow: document.documentElement.scrollWidth > vw + 1, scrollWidth: document.documentElement.scrollWidth, vw, tables, culprits,
    errorState: /Something went wrong|Could not load/i.test(document.body.innerText),
    denied: /Administrator access required/.test(document.body.innerText),
  };
}

async function settle(page) {
  await page.waitForNetworkIdle({ idleTime: 400, timeout: 5000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 250));
}

async function openAs(browser, base, token) {
  const page = await browser.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  await page.goto(base + "/", { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => window.localStorage.setItem("dijione.devToken", t), token);
  return { page, errors };
}

async function clickByText(page, selector, text) {
  return page.evaluate((sel, txt) => {
    const el = [...document.querySelectorAll(sel)].find((e) => e.textContent.trim() === txt || e.getAttribute("aria-label") === txt);
    if (el) { el.click(); return true; }
    return false;
  }, selector, text);
}

async function main() {
  const o = args(process.argv.slice(2));
  const ADMIN = process.env.ADMIN_TOKEN, VIEWER = process.env.VIEWER_TOKEN;
  if (!ADMIN) throw new Error("ADMIN_TOKEN is required (see header).");
  fs.mkdirSync(o.out, { recursive: true });
  const browser = await puppeteer.launch({ headless: true });
  const results = [], failures = [];
  const { page, errors } = await openAs(browser, o.base, ADMIN);
  const shot = async (name) => o.screenshots && page.screenshot({ path: path.join(o.out, `${name}.png`), fullPage: true });
  const check = async (label, w) => {
    const m = await page.evaluate(measure);
    const fail = [];
    if (m.pageOverflow) fail.push(`page overflow ${m.scrollWidth}>${m.vw}`);
    if (w >= 1024 && m.tables.length) fail.push(`table scroll: ${m.tables.map((t) => `${t.caption} ${t.scrollWidth}>${t.clientWidth}`).join("; ")}`);
    if (m.errorState) fail.push("error state shown");
    if (m.denied) fail.push("admin denied");
    results.push({ label, width: w, ...m, ok: !fail.length });
    if (fail.length) failures.push({ label, width: w, fail, culprits: m.culprits });
  };

  for (const w of WIDTHS) {
    await page.setViewport({ width: w, height: HEIGHT });
    for (const r of ROUTES) {
      await page.goto(o.base + r, { waitUntil: "domcontentloaded" });
      await settle(page);
      await check(r, w);
      await shot(`${w}${r.replace(/[^a-z0-9]+/gi, "_")}`);
    }
    // Interactions: Investigate dialog and Map dialog from the Unmapped tab.
    await page.goto(o.base + "/admin/identity?tab=unmapped", { waitUntil: "domcontentloaded" });
    await settle(page);
    const investigated = await page.evaluate(() => {
      const b = document.querySelector('[aria-label^="Investigate ZKBioTime ID"]');
      if (b) b.click();
      return Boolean(b);
    });
    if (investigated) { await settle(page); await check("dialog: investigate", w); await shot(`${w}_dialog_investigate`); await page.keyboard.press("Escape"); }
    else failures.push({ label: "Investigate link", width: w, fail: ["not found"] });
    await settle(page);
    const mapped = await page.evaluate(() => {
      const b = document.querySelector('[aria-label^="Map ZKBioTime ID "]');
      if (b) b.click();
      return Boolean(b);
    });
    if (mapped) { await settle(page); await check("dialog: map", w); await shot(`${w}_dialog_map`); await page.keyboard.press("Escape"); }
    else failures.push({ label: "Map button", width: w, fail: ["not found"] });
    // Readiness drill-down: an outstanding ID opens its investigation view.
    await page.goto(o.base + "/admin/identity?tab=readiness", { waitUntil: "domcontentloaded" });
    await settle(page);
    const drilled = await page.evaluate(() => {
      const b = document.querySelector('[aria-label^="Investigate ZKBioTime ID"]');
      if (b) b.click();
      return Boolean(b);
    });
    await settle(page);
    const dialogOpen = await page.evaluate(() => [...document.querySelectorAll("h2")].some((h) => /^ZKBioTime ID /.test(h.textContent)));
    if (!drilled || !dialogOpen) failures.push({ label: "readiness drill-down", width: w, fail: [drilled ? "dialog did not open" : "no investigate link"] });
    await page.keyboard.press("Escape");
  }

  // Compact Unmapped IDs table: short values never wrap and actions stay on one line.
  for (const w of [1093, 1366, 1440, 1920]) {
    await page.setViewport({ width: w, height: HEIGHT });
    await page.goto(o.base + "/admin/identity?tab=unmapped", { waitUntil: "domcontentloaded" });
    await settle(page);
    const wrap = await page.evaluate(() => {
      const table = [...document.querySelectorAll("table")].find((t) => t.querySelector("caption")?.textContent === "Unmapped ZKBioTime IDs");
      if (!table) return { missing: true };
      const lineHeight = 24; // one text line incl. badge padding
      const tall = [...table.querySelectorAll("td.whitespace-nowrap")]
        .map((td) => [...td.children].map((c) => c.getBoundingClientRect().height))
        .filter((hs) => hs.some((h) => h > lineHeight * 1.6)).length;
      const acts = [...table.querySelectorAll("tbody tr td:last-child span.flex-nowrap")]
        .filter((s) => s.getBoundingClientRect().height > 48).length;
      return { missing: false, tall, acts };
    });
    if (wrap.missing) failures.push({ label: "unmapped table", width: w, fail: ["table not found"] });
    else if (wrap.tall || wrap.acts) failures.push({ label: "unmapped table wraps", width: w, fail: [`${wrap.tall} wrapped value cells, ${wrap.acts} wrapped action groups`] });
    await shot(`${w}_unmapped_compact`);
  }

  // ---- v0.9 -------------------------------------------------------------
  // Blank space below Activity: no nested vertical scroller around the data,
  // and the gap between the pager and the end of the page stays within padding.
  const blank = () => {
    const nested = [...document.querySelectorAll("main *")].filter((el) => {
      if (el.closest('[role="dialog"], [aria-modal="true"]')) return false;
      const s = getComputedStyle(el);
      return (s.overflowY === "auto" || s.overflowY === "scroll") && el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 40;
    }).map((el) => String(el.className).slice(0, 60));
    const pager = [...document.querySelectorAll("nav, div")].filter((el) => /Next page|Previous page/.test(el.innerHTML) && el.querySelector("button"))
      .map((el) => el.getBoundingClientRect().bottom + window.scrollY).sort((a, b) => b - a)[0];
    const doc = document.documentElement.scrollHeight;
    const gap = pager ? Math.round(doc - pager) : null;
    return { nested, gap, doc, vh: window.innerHeight };
  };
  for (const [w, h] of [[1366, 768], [1440, 900], [1920, 1080]]) {
    await page.setViewport({ width: w, height: h });
    for (const r of ["/activity?view=events&size=10", "/activity?view=events&size=50", "/activity?view=events&size=100",
      "/activity?size=10", "/activity?size=50", "/activity?size=100"]) {
      await page.goto(o.base + r, { waitUntil: "domcontentloaded" });
      await settle(page);
      const b = await page.evaluate(blank);
      const fail = [];
      if (b.nested.length) fail.push(`nested vertical scroller: ${b.nested.join(" | ")}`);
      if (b.doc > b.vh && (b.gap === null || b.gap > 160)) fail.push(`gap below pager ${b.gap}px`);
      results.push({ label: `blank-space ${r}`, width: w, height: h, ...b, ok: !fail.length });
      if (fail.length) failures.push({ label: `blank-space ${r}`, width: w, fail });
      if (r.endsWith("size=100")) await shot(`${w}x${h}_blank_${r.includes("events") ? "events" : "daily"}_100`);
    }
  }
  // Expanded details keep the page flowing (no inner scroller after expansion).
  await page.setViewport({ width: 1366, height: 768 });
  await page.goto(o.base + "/activity?view=events&size=50", { waitUntil: "domcontentloaded" });
  await settle(page);
  await page.evaluate(() => document.querySelector('[aria-label^="Show details for"]')?.click());
  await settle(page);
  const expanded = await page.evaluate(blank);
  if (expanded.nested.length) failures.push({ label: "blank-space expanded details", width: 1366, fail: expanded.nested });
  const groups = await page.evaluate(() => ["Fingerprint record", "Identity", "Device & source"].every((t) => document.querySelector(`section[aria-label="${t}"]`))
    && [...document.querySelectorAll("summary")].some((s) => s.textContent === "Technical details"));
  if (!groups) failures.push({ label: "activity detail groups", width: 1366, fail: ["grouped details missing"] });
  await shot("1366_activity_details_grouped");

  // Daily summary, extremes, export dialog, review dialog, Access page, forbidden wording.
  for (const w of [1366, 375]) {
    await page.setViewport({ width: w, height: HEIGHT });
    await page.goto(o.base + "/activity", { waitUntil: "domcontentloaded" });
    await settle(page);
    const daily = await page.evaluate(() => ({
      cards: Boolean(document.querySelector('[aria-label="Identity-days by mapping status"]')),
      single: document.body.innerText.includes("Single Recorded Fingerprint"),
      raw: /ZKBioTime ID \d/.test(document.body.innerText),
    }));
    if (!daily.cards || !daily.single || !daily.raw) failures.push({ label: "daily summary", width: w, fail: [JSON.stringify(daily)] });
    await shot(`${w}_activity_daily`);
    const opened = await clickByText(page, "button", "Review…");
    await settle(page);
    const dlg = await page.evaluate(() => ({ title: /Attendance review/i.test(document.body.innerText),
      evidence: /Recorded evidence \(current\)/i.test(document.body.innerText) }));
    if (!opened || !dlg.title || !dlg.evidence) failures.push({ label: "review dialog", width: w, fail: [JSON.stringify({ opened, ...dlg })] });
    await check("dialog: attendance review", w);
    await shot(`${w}_dialog_review`);
    await page.keyboard.press("Escape");
    await settle(page);
    const exp = await clickByText(page, "button", "Export report…");
    await settle(page);
    const expOk = await page.evaluate(() => Boolean(document.querySelector('select[aria-label="Report type"]')));
    if (!exp || !expOk) failures.push({ label: "export dialog", width: w, fail: ["not opened"] });
    await check("dialog: export report", w);
    await shot(`${w}_dialog_export`);
    await page.keyboard.press("Escape");
    await page.goto(o.base + "/?from=2026-11-18&to=2026-11-18", { waitUntil: "domcontentloaded" });
    await settle(page);
    const ext = await page.evaluate(() => /Earliest Recorded Fingerprint/i.test(document.body.innerText) && /Latest Recorded Fingerprint/i.test(document.body.innerText));
    if (!ext) failures.push({ label: "extremes cards", width: w, fail: ["missing"] });
    await shot(`${w}_overview_extremes`);
  }
  for (const r of ["/", "/today", "/activity", "/activity?view=events", "/exceptions", "/employees"]) {
    await page.goto(o.base + r, { waitUntil: "domcontentloaded" });
    await settle(page);
    const bad = await page.evaluate(() => (document.body.innerText.match(/First Arrival|Last Departure|Check-?out|Clock out|Exit time|Working hours/gi) || []));
    if (bad.length) failures.push({ label: `forbidden wording ${r}`, width: 375, fail: bad });
  }
  await page.setViewport({ width: 1366, height: HEIGHT });
  await page.goto(o.base + "/admin/access", { waitUntil: "domcontentloaded" });
  await settle(page);
  const access = await page.evaluate(() => ({
    nav: [...document.querySelectorAll("a")].some((a) => a.textContent.trim() === "Access"),
    order: [...document.querySelectorAll("a")].map((a) => a.textContent.trim()).filter((t) => ["Identity Management", "Sites", "Access", "Site Health"].includes(t)),
  }));
  if (!access.nav) failures.push({ label: "access nav", width: 1366, fail: ["Access link missing for On-site Admin"] });
  if (access.order.slice(0, 4).join(",") !== "Identity Management,Sites,Access,Site Health") failures.push({ label: "admin nav order", width: 1366, fail: [access.order.join(",")] });
  await shot("1366_admin_access");

  // ---- v0.9 closure ------------------------------------------------------
  // Add Person: directory search dialog, results with avatar/initials, confirmation step.
  for (const w of [1366, 375]) {
    await page.setViewport({ width: w, height: HEIGHT });
    await page.goto(o.base + "/admin/access", { waitUntil: "domcontentloaded" });
    await settle(page);
    if (!(await clickByText(page, "button", "Add person"))) { failures.push({ label: "add person", width: w, fail: ["button missing"] }); continue; }
    await settle(page);
    const input = await page.$('input[id="access-search"]');
    if (!input) { failures.push({ label: "add person", width: w, fail: ["search input missing"] }); continue; }
    await input.type("ta", { delay: 30 });
    await new Promise((r) => setTimeout(r, 900));
    await settle(page);
    const res = await page.evaluate(() => ({
      label: /Search Microsoft Entra ID/.test(document.body.innerText),
      results: document.querySelectorAll('ul[aria-label="Directory search results"] li').length,
    }));
    if (!res.label || !res.results) failures.push({ label: "add person search", width: w, fail: [JSON.stringify(res)] });
    await check("dialog: add person", w);
    await shot(`${w}_add_person_results`);
    const selected = await page.evaluate(() => {
      const b = [...document.querySelectorAll('ul[aria-label="Directory search results"] button')].find((x) => !x.disabled);
      if (b) b.click();
      return Boolean(b);
    });
    await settle(page);
    if (selected) { await check("dialog: confirm access", w); await shot(`${w}_add_person_confirm`); }
    await page.keyboard.press("Escape");
  }

  // Charts: smooth brand gradients only, never textures / patterns.
  await page.setViewport({ width: 1440, height: HEIGHT });
  await page.goto(o.base + "/?from=2026-11-18&to=2026-11-18", { waitUntil: "domcontentloaded" });
  await settle(page);
  const textures = await page.evaluate(() => [...document.querySelectorAll('[class*="onsite-bar-"]')]
    .map((el) => getComputedStyle(el).backgroundImage).filter((b) => /repeating|radial/.test(b)).length);
  if (textures) failures.push({ label: "chart textures", width: 1440, fail: [`${textures} textured elements`] });
  await shot("1440_overview_charts_brand");
  await page.goto(o.base + "/admin/identity?tab=overview", { waitUntil: "domcontentloaded" });
  await settle(page);
  await shot("1440_identity_charts_brand");

  // Activity summary cards filter the Daily summary and keep the other filters.
  await page.goto(o.base + "/activity?term=Main%20Door", { waitUntil: "domcontentloaded" });
  await settle(page);
  for (const [card, mapping] of [["Unmapped", "unmapped"], ["Mapping conflict", "conflict"], ["Verified", "verified"]]) {
    await page.evaluate((c) => [...document.querySelectorAll('[aria-label="Identity-days by mapping status"] button')]
      .find((b) => b.getAttribute("aria-label").startsWith(c))?.click(), card);
    await settle(page);
    const st = await page.evaluate(() => ({
      url: location.search,
      pressed: [...document.querySelectorAll('[aria-label="Identity-days by mapping status"] button[aria-pressed="true"]')].map((b) => b.getAttribute("aria-label").split(":")[0]),
      badges: [...document.querySelectorAll('table[aria-label], table')].length,
    }));
    if (!st.url.includes(`mapping=${mapping}`) || !st.url.includes("term=") || st.pressed[0] !== card) {
      failures.push({ label: `summary card ${card}`, width: 1440, fail: [JSON.stringify(st)] });
    }
    results.push({ label: `summary card ${card}`, width: 1440, ok: true, ...st });
    await shot(`1440_activity_card_${mapping}`);
  }

  // Activity: all mapping states with the reconciled summary strip.
  await page.setViewport({ width: 1366, height: HEIGHT });
  await page.goto(o.base + "/activity?view=events", { waitUntil: "domcontentloaded" });
  await settle(page);
  const act = await page.evaluate(() => ({
    strip: Boolean(document.querySelector('[aria-label="Recorded events by mapping status"]')),
    unverified: document.body.innerText.includes("Not mapped to a team member"),
  }));
  if (!act.strip) failures.push({ label: "activity summary strip", width: 1366, fail: ["missing"] });
  results.push({ label: "activity: unverified rows present", width: 1366, ok: act.unverified, unverified: act.unverified });
  await shot("1366_activity_all");

  // Collapsed navigation: the content takes the freed width, nothing overflows.
  await page.evaluate(() => window.localStorage.setItem("onsite.nav.collapsed", "1"));
  for (const w of COLLAPSED_WIDTHS) {
    await page.setViewport({ width: w, height: HEIGHT });
    for (const r of ["/", "/activity", "/employees", "/admin/identity?tab=unmapped"]) {
      await page.goto(o.base + r, { waitUntil: "domcontentloaded" });
      await settle(page);
      await check(`collapsed ${r}`, w);
      const rail = await page.evaluate(() => document.querySelector("aside[data-collapsed]")?.getBoundingClientRect().width ?? 0);
      if (rail < 56 || rail > 72) failures.push({ label: `collapsed rail ${r}`, width: w, fail: [`rail width ${rail}`] });
      await shot(`${w}_collapsed${r.replace(/[^a-z0-9]+/gi, "_")}`);
    }
  }
  await page.evaluate(() => window.localStorage.removeItem("onsite.nav.collapsed"));

  // Period filter: the Overview refetches for a different period.
  await page.setViewport({ width: 1280, height: HEIGHT });
  await page.goto(o.base + "/admin/identity?tab=overview", { waitUntil: "domcontentloaded" });
  await settle(page);
  if (!(await clickByText(page, "button", "Last 7 days"))) failures.push({ label: "period preset", width: 1280, fail: ["Last 7 days not found"] });
  await settle(page);
  if (!page.url().includes("from=")) failures.push({ label: "period preset", width: 1280, fail: ["period not kept in URL"] });

  // Viewer permission boundary.
  if (VIEWER) {
    await page.evaluate((t) => window.localStorage.setItem("dijione.devToken", t), VIEWER);
    for (const r of ["/admin/identity", "/employees"]) {
      await page.goto(o.base + r, { waitUntil: "domcontentloaded" });
      await settle(page);
      const m = await page.evaluate(measure);
      const expectDenied = r.startsWith("/admin");
      if (m.denied !== expectDenied) failures.push({ label: `viewer ${r}`, width: 1280, fail: [`denied=${m.denied}`] });
    }
  }
  await browser.close();
  const report = { when: new Date().toISOString(), checks: results.length, failures, consoleErrors: [...new Set(errors)] };
  fs.writeFileSync(path.join(o.out, "results.json"), JSON.stringify({ ...report, results }, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log(`\n${results.length} layout checks, ${failures.length} failure(s). Output: ${o.out}`);
  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
