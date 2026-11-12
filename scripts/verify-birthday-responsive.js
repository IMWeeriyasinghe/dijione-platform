#!/usr/bin/env node
/**
 * npm run birthday:responsive-check
 *
 * Round 4 — a committed, reusable responsive-audit tool for the whole
 * DijiBirthday app (apps/birthday-web), not a one-page scratch script.
 * Drives real Chromium (Puppeteer, already in node_modules — no new
 * dependency) through every route in the app at the standing DijiOne
 * viewport matrix, and asserts the one non-negotiable invariant on every
 * page: `document.documentElement.scrollWidth <= window.innerWidth`.
 * Also drives the highest-risk modal (Add/Edit Supplier User) through the
 * viewport-cap/scroll verification that a jsdom unit test cannot prove.
 *
 * REQUIRES a live local stack: platform-api (8000), birthday-api (8003,
 * with INTEGRATIONS_MODE=mock so employee data actually loads), and
 * birthday-web (3003, `npm run dev` from apps/birthday-web). Mint a dev
 * token first:
 *
 *   curl -s -X POST http://localhost:8000/api/auth/dev-login \
 *     -H "Content-Type: application/json" -d '{"persona_key":"super-admin"}' \
 *     | node -e "process.stdin.on('data',d=>console.log(JSON.parse(d).access_token))"
 *
 * Then:
 *
 *   DEV_TOKEN=<token> npm run birthday:responsive-check
 *   DEV_TOKEN=<token> npm run birthday:responsive-check -- --screenshots
 *
 * Flags:
 *   --base-url <url>     default http://localhost:3003/birthday
 *   --api-url <url>      default http://localhost:8003 (birthday-api, for
 *                         self-seeding deterministic order/supplier IDs)
 *   --screenshots        also capture PNGs (off by default — not every run
 *                         needs image files)
 *
 * Not wired into CI (requires a live local stack CI doesn't currently
 * provision for birthday-web). Generated output under `responsive-audit/`
 * (JSON results + screenshots) is a run artifact — never committed.
 */
"use strict";

const puppeteer = require("puppeteer");
const path = require("path");
const fs = require("fs");

const REPO_ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(REPO_ROOT, "responsive-audit");

const WIDTHS = [1920, 1440, 1280, 1180, 1024, 900, 768, 430, 390];
const HEIGHT = 1000;
// Short/landscape mobile — the exact scenario the Modal `dvh` fix targets.
const SHORT_HEIGHTS = [{ width: 430, height: 390 }, { width: 812, height: 375 }];

function parseArgs(argv) {
  let baseUrl = "http://localhost:3003/birthday";
  let apiUrl = "http://localhost:8003";
  let screenshots = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--base-url") baseUrl = argv[++i];
    else if (argv[i] === "--api-url") apiUrl = argv[++i];
    else if (argv[i] === "--screenshots") screenshots = true;
  }
  return { baseUrl, apiUrl, screenshots };
}

/** Real-browser diagnostic: which visible, non-zero-size element(s) extend
 * past the viewport's right edge, causing document-level overflow. Skips
 * anything display:none/visibility:hidden/opacity:0/zero-size (a closed
 * drawer, an off-canvas nav, a hidden desktop/mobile variant of a
 * responsive pair) and anything that's just scrolling inside its own
 * intentional overflow-x-auto container (e.g. a wide table on a narrow
 * screen) rather than pushing the whole page wider. */
function findOverflowCulprits() {
  /* eslint-disable no-undef */
  const vw = window.innerWidth;
  const results = [];
  const all = document.querySelectorAll("body *");
  for (const el of all) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (rect.right <= vw + 1) continue;

    // Allowed local scroll: this element (or an ancestor) is itself an
    // intentionally horizontally-scrollable container (overflow-x: auto/
    // scroll) — its content may be genuinely wider than the container by
    // design (e.g. Table.tsx's own overflow-x-auto wrapper). That's fine
    // as long as it doesn't widen the DOCUMENT itself, which is checked
    // separately by the caller via document.documentElement.scrollWidth.
    let node = el;
    let insideScrollContainer = false;
    while (node && node !== document.body) {
      const s = getComputedStyle(node);
      if ((s.overflowX === "auto" || s.overflowX === "scroll") && node !== el) {
        insideScrollContainer = true;
        break;
      }
      node = node.parentElement;
    }
    if (insideScrollContainer) continue;

    results.push({
      tag: el.tagName.toLowerCase(),
      className: typeof el.className === "string" ? el.className.slice(0, 120) : "",
      right: Math.round(rect.right),
      text: (el.textContent || "").trim().slice(0, 60),
    });
  }
  return results.slice(0, 10);
  /* eslint-enable no-undef */
}

async function assertNoOverflow(page, label, issues) {
  const measurements = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  if (measurements.scrollWidth > measurements.innerWidth + 1) {
    const culprits = await page.evaluate(findOverflowCulprits);
    issues.push({
      label,
      message: `WHOLE-PAGE OVERFLOW: scrollWidth=${measurements.scrollWidth} > innerWidth=${measurements.innerWidth}`,
      culprits,
    });
    return false;
  }
  return true;
}

/** Deterministic seed IDs — reads the birthday-api directly (not through
 * the Next.js app) so the audit doesn't depend on manual fixture setup.
 * Picks the first existing order/supplier if any exist; if none exist,
 * this is reported as a setup problem rather than silently skipped. */
async function resolveSeedIds(apiUrl, token) {
  const headers = { Authorization: `Bearer ${token}` };
  const orderRes = await fetch(`${apiUrl}/api/birthday/orders?page_size=1`, { headers });
  const orderData = await orderRes.json();
  const orderId = orderData.items?.[0]?.id ?? null;

  const supplierRes = await fetch(`${apiUrl}/api/birthday/suppliers?page_size=1`, { headers });
  const supplierData = await supplierRes.json();
  const supplierId = supplierData.items?.[0]?.id ?? null;

  return { orderId, supplierId };
}

const ROUTES = (orderId, supplierId) => [
  { name: "dashboard", path: "/", readyText: "Upcoming (14 days)" },
  { name: "upcoming", path: "/upcoming", readyText: null }, // verified via table/card presence below
  { name: "orders", path: "/orders", readyText: null },
  ...(orderId != null ? [{ name: "order-detail", path: `/orders/${orderId}`, readyText: null }] : []),
  { name: "suppliers", path: "/suppliers", readyText: null },
  ...(supplierId != null ? [{ name: "supplier-detail", path: `/suppliers/${supplierId}`, readyText: null }] : []),
  { name: "inbound-emails", path: "/inbound-emails", readyText: "Unmatched supplier email" },
];

async function waitForReady(page, route) {
  // Generic readiness: wait for the loading spinner (if any) to disappear,
  // then settle briefly — avoids a false "OK" on a still-loading page
  // without hand-writing a selector per route.
  try {
    await page.waitForFunction(
      () => !document.body.textContent?.includes("Loading"),
      { timeout: 8000 }
    );
  } catch {
    // A route with no loading text (e.g. a route handler) — fine.
  }
  if (route.readyText) {
    try {
      await page.waitForFunction(
        (text) => document.body.textContent?.includes(text),
        { timeout: 8000 },
        route.readyText
      );
    } catch {
      // Content may differ (empty state) — the overflow check still runs.
    }
  }
  await new Promise((r) => setTimeout(r, 300));
}

async function runRouteMatrix(browser, baseUrl, token, orderId, supplierId, screenshots) {
  const page = await browser.newPage();
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => window.localStorage.setItem("dijione.devToken", t), token);

  const routes = ROUTES(orderId, supplierId);
  const allIssues = [];
  const perRoute = {};

  for (const route of routes) {
    const routeResults = [];
    const routeDir = path.join(OUT_DIR, route.name);
    if (screenshots) fs.mkdirSync(routeDir, { recursive: true });

    for (const width of WIDTHS) {
      await page.setViewport({ width, height: HEIGHT });
      await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
      await waitForReady(page, route);

      const issues = [];
      await assertNoOverflow(page, `${route.name}@${width}`, issues);
      routeResults.push({ width, issues });
      allIssues.push(...issues);

      if (screenshots) {
        await page.screenshot({ path: path.join(routeDir, `${width}.png`), fullPage: true });
      }

      console.log(
        `[${route.name}] ${width}px — ${issues.length === 0 ? "OK" : `${issues.length} issue(s)`}`
      );
      for (const issue of issues) {
        console.log(`  ${issue.message}`);
        for (const c of issue.culprits ?? []) {
          console.log(`    <${c.tag} class="${c.className}"> right=${c.right} "${c.text}"`);
        }
      }
    }
    perRoute[route.name] = routeResults;
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(path.join(OUT_DIR, `${route.name}.json`), JSON.stringify(routeResults, null, 2));
  }

  await page.close();
  return { perRoute, allIssues };
}

/** Real-Chromium verification for the Modal fix (§8 of the round 4
 * request) — the authoritative proof unit tests cannot provide. Targets
 * the tallest modal (Add/Edit Supplier User) at short/landscape mobile
 * dimensions. */
async function runModalCheck(browser, baseUrl, token, supplierId) {
  const issues = [];
  if (supplierId == null) {
    console.log("[modal] skipped — no seeded supplier to open a Supplier User modal on");
    return issues;
  }

  const page = await browser.newPage();
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => window.localStorage.setItem("dijione.devToken", t), token);

  for (const { width, height } of SHORT_HEIGHTS) {
    await page.setViewport({ width, height });
    await page.goto(`${baseUrl}/suppliers/${supplierId}`, { waitUntil: "domcontentloaded" });
    try {
      await page.waitForFunction(() => !document.body.textContent?.includes("Loading"), { timeout: 8000 });
      await page.waitForFunction(
        () => Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.includes("Add Supplier User")),
        { timeout: 8000 }
      );
    } catch {
      // fall through — the "trigger not found" issue below reports it clearly
    }
    await new Promise((r) => setTimeout(r, 300));

    const opened = await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll("button")).find((b) =>
        b.textContent?.includes("Add Supplier User")
      );
      if (!btn) return false;
      btn.click();
      return true;
    });
    if (!opened) {
      issues.push({ label: `modal@${width}x${height}`, message: "Add Supplier User trigger not found (not admin, or no supplier)" });
      continue;
    }
    await new Promise((r) => setTimeout(r, 300));

    const check = await page.evaluate(() => {
      const dialogHeading = Array.from(document.querySelectorAll("h2")).find((h) => h.textContent?.includes("Supplier User"));
      const panel = dialogHeading?.closest('[class*="max-h-"]');
      if (!panel) return { found: false };
      const rect = panel.getBoundingClientRect();
      const withinViewport = rect.top >= 0 && rect.bottom <= window.innerHeight + 1;
      const scrollWidthOk = document.documentElement.scrollWidth <= window.innerWidth + 1;

      // The scrollable body is the panel's second direct child (header,
      // then body wrapper) per Modal.tsx's structure.
      const bodyWrapper = panel.children[1];
      const scrollable = bodyWrapper ? bodyWrapper.scrollHeight > bodyWrapper.clientHeight : false;
      if (bodyWrapper) bodyWrapper.scrollTop = bodyWrapper.scrollHeight;

      const closeBtn = document.querySelector('button[aria-label="Close dialog"]');
      const closeVisible = closeBtn ? closeBtn.getBoundingClientRect().height > 0 : false;

      return { found: true, withinViewport, scrollWidthOk, scrollable, closeVisible, panelRect: rect };
    });

    if (!check.found) {
      issues.push({ label: `modal@${width}x${height}`, message: "Modal panel not found after opening" });
      continue;
    }
    if (!check.withinViewport) {
      issues.push({ label: `modal@${width}x${height}`, message: `Panel extends outside viewport: ${JSON.stringify(check.panelRect)}` });
    }
    if (!check.scrollWidthOk) {
      issues.push({ label: `modal@${width}x${height}`, message: "Opening the modal caused document-level horizontal overflow" });
    }
    if (!check.closeVisible) {
      issues.push({ label: `modal@${width}x${height}`, message: "Close button not visible" });
    }

    // Escape closes it.
    await page.keyboard.press("Escape");
    await new Promise((r) => setTimeout(r, 200));
    const stillOpen = await page.evaluate(() =>
      Array.from(document.querySelectorAll("h2")).some((h) => h.textContent?.includes("Supplier User"))
    );
    if (stillOpen) {
      issues.push({ label: `modal@${width}x${height}`, message: "Escape did not close the modal" });
    }

    console.log(
      `[modal] ${width}x${height} — withinViewport=${check.withinViewport} scrollable=${check.scrollable} closeVisible=${check.closeVisible} escapeCloses=${!stillOpen}`
    );
  }

  await page.close();
  return issues;
}

async function main() {
  const { baseUrl, apiUrl, screenshots } = parseArgs(process.argv.slice(2));
  const token = process.env.DEV_TOKEN;
  if (!token) {
    console.error("DEV_TOKEN env var is required — mint one via POST /api/auth/dev-login (see header comment).");
    process.exit(2);
  }

  console.log(`Resolving deterministic seed IDs from ${apiUrl} ...`);
  const { orderId, supplierId } = await resolveSeedIds(apiUrl, token);
  console.log(`  order id: ${orderId ?? "(none found — order-detail route skipped)"}`);
  console.log(`  supplier id: ${supplierId ?? "(none found — supplier-detail route skipped)"}`);

  const browser = await puppeteer.launch({ headless: "new" });

  const { allIssues: routeIssues } = await runRouteMatrix(browser, baseUrl, token, orderId, supplierId, screenshots);
  const modalIssues = await runModalCheck(browser, baseUrl, token, supplierId);

  await browser.close();

  const totalIssues = routeIssues.length + modalIssues.length;
  console.log(`\n=== SUMMARY: ${totalIssues} total issue(s) ===`);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(
    path.join(OUT_DIR, "summary.json"),
    JSON.stringify({ routeIssues, modalIssues }, null, 2)
  );
  process.exit(totalIssues > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
