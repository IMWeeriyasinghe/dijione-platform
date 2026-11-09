import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { STATE_FILE } from "../playwright.config";

// Only the identity lookup is mocked. Every /api/talent call reaches a real
// talent-api, which checks the signed token itself.
const seed = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
const TOKEN_KEY = "dijione.devToken";
const ROLES = {
  ta: { id: 201, name: "Tara Member", role: "TA_MEMBER", client_id: null },
  cs: { id: 202, name: "Casey Success", role: "CUSTOMER_SUCCESS", client_id: null },
  restricted: { id: 203, name: "Riley Restricted", role: "TA_MEMBER", client_id: null },
  client: { id: 204, name: "Cleo Client", role: "TALENT_CLIENT", client_id: seed.alpha },
} as const;
type Persona = keyof typeof ROLES;

function me(persona: Persona, moduleRoles?: unknown[]) {
  const p = ROLES[persona];
  return {
    id: p.id, full_name: p.name, email: `${persona}@example.invalid`, is_active: true,
    platform_role: "PLATFORM_USER", platform_permissions: [],
    module_roles: moduleRoles ?? [{ module_key: "talent-flow", role: p.role, client_id: p.client_id, permissions: [] }],
  };
}

async function identity(page: Page, handler: () => { status: number; json: unknown }) {
  await page.route("**/api/auth/me", (route) => route.fulfill(handler()));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: { auth_mode: "entra" } }));
  await page.route("**/api/auth/logout", (route) => route.fulfill({ json: { logout_url: null } }));
  await page.route("**/api/notifications**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/talent/recruitment/**", (route) => route.fulfill({ json: { provider: "LEVER", last_successful_sync_at: null, latest_run: null } }));
}

async function signIn(page: Page, persona: Persona) {
  await identity(page, () => ({ status: 200, json: me(persona) }));
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), [TOKEN_KEY, seed.staff[persona]]);
}

function talentApi(request: import("@playwright/test").APIRequestContext, persona: Persona, path: string) {
  return request.get(`${seed.api}/api/talent${path}`, { headers: { Authorization: `Bearer ${seed.staff[persona]}` } });
}

async function portalCandidates(request: import("@playwright/test").APIRequestContext) {
  const redeem = await request.post(`${seed.api}/api/talent/external/redeem`, { data: { token: seed.tokens.alpha } });
  const { access_token } = await redeem.json();
  const res = await request.get(`${seed.api}/api/talent/external/requests/${seed.alpha_request}/candidates`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  return res.text();
}

const stored = (page: Page) => page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY);
const LOAD = { timeout: 45_000 };

test("signed-out users get the DijiOne sign-in, not the workspace", async ({ page }) => {
  await identity(page, () => ({ status: 401, json: {} }));
  await page.goto("/talent-flow/dashboard");
  await expect(page.getByRole("button", { name: /microsoft/i })).toBeVisible(LOAD);
  await expect(page.getByText("Operations Dashboard")).toHaveCount(0);
});

test("a user with no TalentFlow role is refused", async ({ page }) => {
  await identity(page, () => ({ status: 200, json: me("ta", []) }));
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), [TOKEN_KEY, seed.staff.ta]);
  await page.goto("/talent-flow/dashboard");
  await expect(page.getByText("No DijiTalentFlow access")).toBeVisible(LOAD);
});

test("an expired session returns to sign-in and clears the token", async ({ page }) => {
  await identity(page, () => ({ status: 401, json: {} }));
  await page.addInitScript(([k, v]) => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem(k, v); sessionStorage.setItem("seeded", "1"); } }, [TOKEN_KEY, "expired"]);
  await page.goto("/talent-flow/dashboard");
  await expect(page.getByRole("button", { name: /microsoft/i })).toBeVisible(LOAD);
  expect(await stored(page)).toBeNull();
});

test("an invalid token is refused by the API", async ({ request }) => {
  const res = await request.get(`${seed.api}/api/talent/requests`, { headers: { Authorization: "Bearer forged" } });
  expect(res.status()).toBe(401);
});

test("logout clears the token and the workspace stays closed", async ({ page }) => {
  await identity(page, () => ({ status: 200, json: me("ta") }));
  // Seeded once, so the reload below proves logout rather than re-seeding.
  await page.addInitScript(([k, v]) => { if (!sessionStorage.getItem("seeded")) { localStorage.setItem(k, v); sessionStorage.setItem("seeded", "1"); } }, [TOKEN_KEY, seed.staff.ta]);
  await page.goto("/talent-flow/dashboard");
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible(LOAD);
  await page.getByRole("button", { name: "User menu" }).click();
  await page.getByRole("button", { name: "Switch persona" }).click();
  await expect.poll(() => stored(page)).toBeNull();
  await expect(page.getByRole("button", { name: /microsoft/i })).toBeVisible(LOAD);
  await page.reload();
  await expect(page.getByRole("button", { name: /microsoft/i })).toBeVisible(LOAD);
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toHaveCount(0);
  expect(await stored(page)).toBeNull();
});

test("TA dashboard shows live counts and navigates", async ({ page }) => {
  await signIn(page, "ta");
  await page.goto("/talent-flow/dashboard");
  await expect(page.getByRole("heading", { name: "Operations Dashboard" })).toBeVisible(LOAD);
  await expect(page.getByText("Active Applications")).toBeVisible();
  await page.getByRole("link", { name: "All Requests" }).click();
  await expect(page.getByText("Alpha Engineer")).toBeVisible(LOAD);
  await expect(page.getByText("Beta Designer")).toBeVisible();
});

test("portfolio-restricted staff see and reach only their clients", async ({ page, request }) => {
  await signIn(page, "restricted");
  await page.goto("/talent-flow/clients");
  await expect(page.getByText("Alpha Test Co").first()).toBeVisible(LOAD);
  await expect(page.getByText("Beta Test Co")).toHaveCount(0);
  await page.goto("/talent-flow/requests");
  await expect(page.getByText("Alpha Engineer")).toBeVisible(LOAD);
  await expect(page.getByText("Beta Designer")).toHaveCount(0);
  expect((await talentApi(request, "restricted", `/requests/${seed.beta_request}`)).status()).toBe(404);
  expect((await talentApi(request, "restricted", `/applications/${seed.bella}`)).status()).not.toBe(200);
});

test("all portfolios are listed for unrestricted staff", async ({ page }) => {
  await signIn(page, "ta");
  await page.goto("/talent-flow/clients");
  await expect(page.getByText("Alpha Test Co").first()).toBeVisible(LOAD);
  await expect(page.getByText("Beta Test Co").first()).toBeVisible();
});

test("staff can move a request through stages", async ({ page, request }) => {
  await signIn(page, "ta");
  await page.goto(`/talent-flow/requests/${seed.alpha_request}`);
  await page.getByRole("button", { name: "Update Stage" }).click(LOAD);
  await page.locator("#stage").selectOption("SCREENING");
  await page.locator("#status-text").fill("");
  await page.locator("form").getByRole("button", { name: "Update Stage" }).click();
  await expect(page.getByText("Screening candidates").first()).toBeVisible(LOAD);
  const body = await (await talentApi(request, "ta", `/requests/${seed.alpha_request}`)).json();
  expect(body.current_stage).toBe("SCREENING");
});

test("sharing a candidate reaches the portal and withdrawing removes them", async ({ page, request }) => {
  await signIn(page, "ta");
  await page.goto(`/talent-flow/requests/${seed.alpha_request}?tab=Candidates`);
  await page.getByRole("button", { name: "Candidates" }).click(LOAD);
  const row = page.getByRole("row").filter({ hasText: "Hana Hidden" });
  const box = row.getByRole("checkbox");
  await expect(box).not.toBeChecked(LOAD);
  expect(await portalCandidates(request)).not.toContain("Hana Hidden");

  await box.check();
  await expect.poll(() => portalCandidates(request), LOAD).toContain("Hana Hidden");
  await box.uncheck();
  await expect.poll(() => portalCandidates(request), LOAD).not.toContain("Hana Hidden");
});

test("applications list shows Lever-owned state read-only", async ({ page }) => {
  await signIn(page, "ta");
  await page.goto("/talent-flow/applications");
  await expect(page.getByRole("row").filter({ hasText: "Sam Shared" })).toBeVisible(LOAD);
  await expect(page.getByText("Synced from Lever").first()).toBeVisible();
});

test("staff can schedule an interview", async ({ page, request }) => {
  const before = (await (await talentApi(request, "ta", "/interviews")).json()).length;
  await signIn(page, "ta");
  await page.goto(`/talent-flow/requests/${seed.alpha_request}`);
  await page.getByRole("button", { name: "Interviews" }).click(LOAD);
  await page.getByRole("button", { name: "Schedule Interview" }).click(LOAD);
  await page.locator("#application").selectOption(String(seed.sam));
  await page.locator("#scheduled-at").fill("2030-01-15T10:00");
  await page.locator("form").getByRole("button", { name: "Schedule", exact: true }).click();
  await expect.poll(async () => (await (await talentApi(request, "ta", "/interviews")).json()).length, LOAD).toBe(before + 1);
});

// Consumes the one pending seed request, so it passes only on the first run
// against a seeded server: --repeat-each fails it by design.
test("TA members cannot review; Customer Success can, once", async ({ browser, request }) => {
  const url = `/talent-flow/requests/${seed.pending_request}`;
  const taContext = await browser.newContext({ baseURL: "http://localhost:3002" });
  const taPage = await taContext.newPage();
  await signIn(taPage, "ta");
  await taPage.goto(url);
  await expect(taPage.getByRole("heading", { name: "Alpha Analyst" })).toBeVisible(LOAD);
  await expect(taPage.getByRole("button", { name: "Review Request" })).toHaveCount(0);
  const forged = await request.post(`${seed.api}/api/talent/requests/${seed.pending_request}/review`, {
    headers: { Authorization: `Bearer ${seed.staff.ta}` }, data: { decision: "APPROVED", reason: "" },
  });
  expect(forged.status()).toBe(403);
  await taContext.close();

  const csContext = await browser.newContext({ baseURL: "http://localhost:3002" });
  const page = await csContext.newPage();
  await signIn(page, "cs");
  await page.goto(url);
  await page.getByRole("button", { name: "Review Request" }).click(LOAD);
  await page.locator("#decision").selectOption("APPROVED");
  await page.locator("form").getByRole("button", { name: "Submit Decision" }).click();
  await expect(page.getByRole("button", { name: "Review Request" })).toHaveCount(0, LOAD);
  const again = await request.post(`${seed.api}/api/talent/requests/${seed.pending_request}/review`, {
    headers: { Authorization: `Bearer ${seed.staff.cs}` }, data: { decision: "REJECTED", reason: "" },
  });
  expect(again.status()).toBe(400);
  await csContext.close();
});

test("the client persona has no staff tools or staff fields", async ({ page, request }) => {
  await signIn(page, "client");
  await page.goto(`/talent-flow/requests/${seed.alpha_request}`);
  await expect(page.getByRole("heading", { name: "Alpha Engineer" })).toBeVisible(LOAD);
  await expect(page.getByRole("button", { name: "Update Stage" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Recruitment Postings" })).toHaveCount(0);

  const stage = await request.post(`${seed.api}/api/talent/requests/${seed.alpha_request}/stage`, {
    headers: { Authorization: `Bearer ${seed.staff.client}` }, data: { stage: "OFFER" },
  });
  expect(stage.status()).toBe(403);
  const body = await (await talentApi(request, "client", `/requests/${seed.alpha_request}`)).text();
  expect(body).not.toContain("internal-note-marker");
  expect((await talentApi(request, "client", `/requests/${seed.beta_request}`)).status()).toBe(404);
});
