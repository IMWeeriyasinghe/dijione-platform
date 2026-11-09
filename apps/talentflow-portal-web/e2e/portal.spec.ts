import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { STATE_FILE } from "../playwright.config";

const seed = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
const INVALID = "This access link is invalid or has expired";
const WELCOME = "Your engagement — Alpha Test Co";
const SESSION = "dijitalent-external-session";
const RAW = "dijitalent-external-raw";
const FORBIDDEN_FIELDS = ["notes", "ta_status", "customer_success_status", "priority", "client_id", "lifecycle_status", "recruiter_notes"];

async function open(page: Page, token: string = seed.tokens.alpha) {
  await page.goto(`/access#${token}`);
  await expect(page.getByText(WELCOME)).toBeVisible({ timeout: 45_000 });
}

const stored = (page: Page, key: string) => page.evaluate((k) => sessionStorage.getItem(k), key);

function api(page: Page, path: string) {
  return page.evaluate(async (p) => {
    const session = sessionStorage.getItem("dijitalent-external-session");
    const res = await fetch(`/api/talent/external${p}`, { headers: { Authorization: `Bearer ${session}` } });
    return { status: res.status, text: await res.text() };
  }, path);
}

async function expectRefused(page: Page, token: string) {
  await page.goto("about:blank"); // a hash-only change would not reload /access
  await page.goto(`/access#${token}`);
  await expect(page.getByText(INVALID)).toBeVisible({ timeout: 45_000 });
  expect(await stored(page, SESSION)).toBeNull();
  expect(page.url()).not.toContain(token);
}

test("a valid link opens the client's workspace and removes the token from the URL", async ({ page }) => {
  await open(page);
  expect(page.url()).not.toContain(seed.tokens.alpha);
  await expect(page.getByText("Alpha Engineer").first()).toBeVisible();
  await expect(page.getByText("Beta Designer")).toHaveCount(0);
});

test("unknown, expired and revoked links are refused alike", async ({ page }) => {
  await expectRefused(page, "not-a-real-token");
  await expectRefused(page, seed.tokens.expired);
  await expectRefused(page, seed.tokens.revoked);
});

// Consumes the one revocable seed grant, so it passes only on the first run
// against a seeded server: --repeat-each fails it by design.
test("revoking a grant ends a live session and clears browser storage", async ({ page, request }) => {
  await open(page, seed.tokens.to_revoke);
  expect(await stored(page, SESSION)).not.toBeNull();
  const revoked = await request.post(`${seed.api}/api/talent/external/grants/${seed.to_revoke_id}/revoke`, {
    headers: { Authorization: `Bearer ${seed.staff.ta}` },
  });
  expect(revoked.status()).toBe(200);

  const direct = await api(page, "/dashboard");
  expect(direct.status).toBe(401);
  await page.reload();
  await expect.poll(() => stored(page, SESSION), { timeout: 30_000 }).toBeNull();
  expect(await stored(page, RAW)).toBeNull();
  await expect(page.getByText(WELCOME)).toHaveCount(0);
});

test("sign out clears the session", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect.poll(() => stored(page, SESSION)).toBeNull();
  expect(await stored(page, RAW)).toBeNull();
});

test("another client's records are refused by the API and the screens", async ({ page }) => {
  await open(page);
  for (const path of [`/requests/${seed.beta_request}`, `/requests/${seed.beta_request}/candidates`, `/applications/${seed.bella}`]) {
    expect((await api(page, path)).status, path).toBe(404);
  }
  const scoped = await api(page, `/requests?client_id=${seed.beta}`);
  expect(scoped.text).not.toContain("Beta Designer");
  await page.goto(`/candidates/${seed.bella}`);
  await expect(page.getByText("Candidate not found")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Bella Beta")).toHaveCount(0);
});

test("only shared candidates appear, and detail navigation works", async ({ page }) => {
  await open(page);
  await page.goto("/requests");
  await page.getByText("Alpha Engineer").first().click();
  await expect(page.getByText("Sam Shared")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Hana Hidden")).toHaveCount(0);
  await page.getByText("Sam Shared").click();
  await expect(page.getByRole("heading", { name: "Sam Shared" })).toBeVisible({ timeout: 30_000 });
});

test("an unshared candidate cannot be opened directly", async ({ page }) => {
  await open(page);
  expect((await api(page, `/applications/${seed.hana}`)).status).toBe(404);
  await page.goto(`/candidates/${seed.hana}`);
  await expect(page.getByText("Candidate not found")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Hana Hidden")).toHaveCount(0);
});

test("interviews show shared candidates only", async ({ page }) => {
  await open(page);
  const body = await api(page, "/interviews");
  expect(body.status).toBe(200);
  expect(body.text).toContain("Sam Shared");
  expect(body.text).not.toContain("Hana Hidden");
  expect(body.text).not.toContain("Bella Beta");
  await page.goto("/interviews");
  await expect(page.getByText("Sam Shared").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Hana Hidden")).toHaveCount(0);
});

test("API responses carry client-safe fields only", async ({ page }) => {
  await open(page);
  const paths = ["/dashboard", "/requests", `/requests/${seed.alpha_request}`, `/requests/${seed.alpha_request}/candidates`, `/applications/${seed.sam}`, "/interviews"];
  for (const path of paths) {
    const { status, text } = await api(page, path);
    expect(status, path).toBe(200);
    expect(text, path).not.toContain("internal-note-marker");
    expect(text, path).not.toContain("recruiter-secret-marker");
    for (const field of FORBIDDEN_FIELDS) expect(text, `${path} ${field}`).not.toContain(`"${field}"`);
  }
  const dashboard = JSON.parse((await api(page, "/dashboard")).text);
  expect(dashboard.candidates_in_process).toBe(1);
});

test("a slow API shows loading, and a failure recovers on retry", async ({ page }) => {
  let mode: "slow" | "fail" | "ok" = "slow";
  await page.route("**/api/talent/external/dashboard", async (route) => {
    if (mode === "fail") return route.fulfill({ status: 500, json: {} });
    if (mode === "slow") await new Promise((r) => setTimeout(r, 5000));
    return route.continue();
  });
  await page.goto(`/access#${seed.tokens.alpha}`);
  await expect(page.getByText("Loading your workspace…")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText(WELCOME)).toBeVisible({ timeout: 30_000 });

  mode = "fail";
  await page.reload();
  const retry = page.getByRole("button", { name: /retry|try again/i });
  await expect(retry).toBeVisible({ timeout: 45_000 });
  mode = "ok";
  await retry.click();
  await expect(page.getByText(WELCOME)).toBeVisible({ timeout: 30_000 });
});

test("no page scrolls horizontally at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await open(page);
  for (const path of ["/", "/requests", `/requests/${seed.alpha_request}`, "/interviews", `/candidates/${seed.sam}`]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
