import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

async function runAxe(page: import("@playwright/test").Page, path: "/" | "/lab" | "/players" | "/results" | "/compare") {
  await page.goto(path, { waitUntil: "domcontentloaded", timeout: 60_000 })
  if (path === "/") {
    await expect(page.getByRole("heading", { name: "Find your matchups." })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("button", { name: "Reload published data" })).toBeEnabled({ timeout: 30_000 })
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
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("golf-model.theme", "dark")
    })
    await page.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
  })

  test("matchup desk / has no critical axe violations", async ({ page }) => {
    const results = await runAxe(page, "/")
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
