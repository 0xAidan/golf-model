import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

async function runAxe(page: import("@playwright/test").Page, path: "/" | "/models" | "/performance" | "/lab" | "/players" | "/results" | "/compare") {
  const reportResponse = path === "/performance" ? page.waitForResponse(response => new URL(response.url()).pathname === "/reports/performance-2026.json") : null
  await page.goto(path, { waitUntil: "domcontentloaded", timeout: 60_000 })
  if (path === "/") {
    await expect(page.getByRole("heading", { name: "Rankings", exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("button", { name: "Reload rankings" })).toBeEnabled({ timeout: 30_000 })
  } else if (path === "/models") {
    await expect(page.getByRole("heading", { name: "Better is something we measure." })).toBeVisible({ timeout: 30_000 })
    await expect(page.locator(".lw-loading")).toHaveCount(0)
    await expect(page.getByRole("heading", { name: "Model runs", exact: true })).toBeVisible()
  } else if (path === "/performance") {
    const response = await reportResponse!
    expect(response.status()).toBe(200)
    expect(response.headers()["content-type"]).toContain("application/json")
    expect(await response.json()).toMatchObject({ schema_version: 1, scopes: { "pre_event|dashboard|all": expect.any(Object) } })
    await expect(page.getByRole("heading", { name: "The event record", exact: true })).toBeVisible({ timeout: 30_000 })
  } else {
    const readyId = {
      "/lab": "lab-command-center", "/players": "players-page",
      "/results": "results-page", "/compare": "compare-page",
    }[path]
    await expect(page.getByTestId(readyId)).toBeVisible({ timeout: 30_000 })
  }
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze()
  return results
}

test.describe("monitoring a11y (critical = 0)", () => {
  test.beforeEach(async ({ page, baseURL }) => {
    if (!baseURL || !["127.0.0.1", "localhost", "[::1]"].includes(new URL(baseURL).hostname)) throw new Error("Accessibility checks require an isolated local preview.")
    await page.route("**/api/**", route => ["GET", "HEAD", "OPTIONS"].includes(route.request().method()) ? route.continue() : route.fulfill({ status: 405, body: "Accessibility checks are read-only" }))
    await page.addInitScript(() => {
      localStorage.setItem("golf-model.theme", "dark")
    })
    await page.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
  })

  test("rankings / has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("models /models has no critical axe violations, including withheld research reports", async ({ page }) => {
    const results = await runAxe(page, "/models")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("performance /performance has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/performance")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("lab /lab has no critical axe violations", async ({ page }) => {
    test.skip(process.env.VITE_COCKPIT_LAB === "0", "Lab route disabled in build")
    const results = await runAxe(page, "/lab")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("players /players has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/players")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("results /results has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/results")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })

  test("compare /compare has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/compare")
    const critical = results.violations.filter((v) => v.impact === "critical")
    expect(critical, JSON.stringify(critical, null, 2)).toHaveLength(0)
  })
})
