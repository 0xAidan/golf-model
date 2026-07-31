import { test, expect } from "@playwright/test"

/**
 * HashRouter-compatible paths until PR 1 migrates to BrowserRouter.
 * Dashboard is `/#/` (or `/`); other routes are `/#/<route>`.
 */
const hash = (path: string): string => {
  if (path === "/" || path === "") return "/#/"
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `/#${normalized}`
}

test.describe("operator terminal core routes", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("golf-model.theme", "dark")
    })
    await page.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
  })

  test("dashboard shows monitoring shell and freshness indicator", async ({ page }) => {
    await page.goto(hash("/"), { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page.getByTestId("monitoring-shell")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId("freshness-indicator")).toBeVisible({ timeout: 15_000 })
  })

  test("results analytics tab loads workspace", async ({ page }) => {
    await page.goto(hash("/results?tab=analytics"), {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    })
    await expect(page.getByTestId("results-page")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId("analytics-workspace")).toBeVisible({ timeout: 30_000 })
  })

  test("system ops health panel visible", async ({ page }) => {
    await page.goto(hash("/system"), { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page.getByTestId("ops-health-panel")).toBeVisible({ timeout: 30_000 })
  })

  test("track-record redirects to analytics", async ({ page }) => {
    await page.goto(hash("/track-record"), { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page).toHaveURL(/tab=analytics/)
    await expect(page.getByTestId("analytics-workspace")).toBeVisible({ timeout: 30_000 })
  })
})
