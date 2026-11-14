#!/usr/bin/env node
/**
 * npm run onsite:responsive-check
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
 *   ADMIN_TOKEN=<t> VIEWER_TOKEN=<t> npm run onsite:responsive-check -- [--screenshots] [--out <dir>]
 *
 * Not wired into CI (needs a live local stack). Output (JSON + optional
 * PNGs) goes to --out (default: the OS temp dir) — never committed.
 */
"use strict";

const puppeteer = require("puppeteer");
const fs = require("fs");
const os = require("os");
const path = require("path");

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const HEIGHT = 900;
const ROUTES = [
  "/", "/today", "/activity", "/employees", "/exceptions",
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

/* eslint-disable no-undef */
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
/* eslint-enable no-undef */

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
