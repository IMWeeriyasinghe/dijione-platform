import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { STATE_FILE } from "../playwright.config";

const seed = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));
const LOAD = { timeout: 45_000 };

// Reported, not fixed here: the design system's colour tokens and its unnamed
// avatar button are shared by every module.
const SHARED = (line: string) => line.includes("color-contrast") || (line.includes("button-name") && line.includes(".p-0"));

async function signIn(page: Page, role: string, id: number, clientId: number | null = null) {
  const profile = {
    id, full_name: "Audit User", email: "audit@example.invalid", is_active: true,
    platform_role: "PLATFORM_USER", platform_permissions: [],
    module_roles: [{ module_key: "talent-flow", role, client_id: clientId, permissions: [] }],
  };
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: profile }));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: { auth_mode: "entra" } }));
  await page.route("**/api/notifications**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/talent/recruitment/**", (route) => route.fulfill({ json: { provider: "LEVER", last_successful_sync_at: null, latest_run: null } }));
}

async function audit(page: Page, label: string) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(async () => {
    const result = await (window as unknown as { axe: { run: (c: unknown, o: unknown) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] });
    return result.violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.slice(0, 4).map((n) => n.target.join(" ")).join(" | ")} (${v.nodes.length})`);
  });
  console.log(`AXE ${label}: ${violations.length ? "\n  " + violations.join("\n  ") : "clean"}`);
  expect(violations.filter((v) => !SHARED(v)), label).toEqual([]);
}

const STAFF = ["dashboard", "clients", "requests", "applications", "candidates", "interviews", "postings", "access-links"];
for (const path of STAFF) {
  test(`staff ${path}`, async ({ page }) => {
    await signIn(page, "TA_MANAGER", 201);
    await page.addInitScript(([k, v]) => localStorage.setItem(k, v), ["dijione.devToken", seed.staff.ta]);
    await page.goto(`/talent-flow/${path}`);
    await expect(page.getByRole("main").first()).toBeVisible(LOAD);
    await page.waitForLoadState("networkidle");
    await audit(page, path);
  });
}
for (const tab of ["Overview", "Candidates", "Interviews", "Messages", "Documents"]) {
  test(`request tab ${tab}`, async ({ page }) => {
    await signIn(page, "TA_MEMBER", 201);
    await page.addInitScript(([k, v]) => localStorage.setItem(k, v), ["dijione.devToken", seed.staff.ta]);
    await page.goto(`/talent-flow/requests/${seed.alpha_request}`);
    await page.getByRole("button", { name: tab }).click(LOAD);
    await page.waitForLoadState("networkidle");
    await audit(page, `request/${tab}`);
  });
}
test("keyboard users can reach the page and see focus", async ({ page }) => {
  await signIn(page, "TA_MEMBER", 201);
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), ["dijione.devToken", seed.staff.ta]);
  await page.goto("/talent-flow/requests");
  await expect(page.getByLabel("Filter by stage")).toBeVisible(LOAD);
  await page.getByLabel("Filter by stage").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Filter by status")).toBeFocused();
  const ring = await page.getByLabel("Filter by status").evaluate((el) => { const c = getComputedStyle(el); return `${c.outlineStyle} ${c.boxShadow}`; });
  expect(ring).not.toBe("none none");
});

test("schedule dialog is labelled and closes with Escape", async ({ page }) => {
  await signIn(page, "TA_MEMBER", 201);
  await page.addInitScript(([k, v]) => localStorage.setItem(k, v), ["dijione.devToken", seed.staff.ta]);
  await page.goto(`/talent-flow/requests/${seed.alpha_request}`);
  await page.getByRole("button", { name: "Interviews" }).click(LOAD);
  await page.getByRole("button", { name: "Schedule Interview" }).click(LOAD);
  await page.locator("#scheduled-at").waitFor();
  await audit(page, "schedule dialog");
  await page.locator("#scheduled-at").focus();
  await expect(page.locator("#scheduled-at")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#scheduled-at")).toHaveCount(0);
});
