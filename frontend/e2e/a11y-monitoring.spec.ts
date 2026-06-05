import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

async function runAxe(page: import("@playwright/test").Page, path: string) {
  await page.goto(path, { waitUntil: "domcontentloaded", timeout: 60_000 })
  await page.waitForTimeout(1500)
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

  test("dashboard / has no critical axe violations", async ({ page }) => {
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
})
