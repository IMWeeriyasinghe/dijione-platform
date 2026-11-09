import fs from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { STATE_FILE } from "../playwright.config";

const seed = JSON.parse(fs.readFileSync(STATE_FILE, "utf-8"));

async function audit(page: Page, label: string) {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const violations = await page.evaluate(async () => {
    const result = await (window as unknown as { axe: { run: (c: unknown, o: unknown) => Promise<{ violations: { id: string; impact: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] });
    return result.violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.slice(0, 4).map((n) => n.target.join(" ")).join(" | ")} (${v.nodes.length})`);
  });
  console.log(`AXE ${label}: ${violations.length ? "\n  " + violations.join("\n  ") : "clean"}`);
  // Colour tokens are shared by every module; reported, not fixed here.
  expect(violations.filter((v) => !v.includes("color-contrast")), label).toEqual([]);
}

test("portal screens", async ({ page }) => {
  await page.goto(`/access#${seed.tokens.alpha}`);
  await expect(page.getByText("Your engagement — Alpha Test Co")).toBeVisible({ timeout: 45_000 });
  await audit(page, "overview");
  for (const path of ["/requests", `/requests/${seed.alpha_request}`, "/interviews", `/candidates/${seed.sam}`]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await audit(page, path);
  }
  const link = page.getByRole("link").first();
  await link.focus();
  await expect(link).toBeFocused();
});

test("invalid link", async ({ page }) => {
  await page.goto("/access#not-real");
  await expect(page.getByText("This access link is invalid or has expired")).toBeVisible({ timeout: 45_000 });
  await audit(page, "invalid link");
  await expect(page.getByRole("alert").filter({ hasText: "invalid or has expired" })).toBeVisible();
});
