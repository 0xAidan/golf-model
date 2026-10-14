import { test, expect } from "@playwright/test"

test.describe("operator terminal core routes", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("golf-model.theme", "dark")
    })
    await page.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
  })

  test("home loads the matchup desk from its local read-only endpoint", async ({ page }) => {
    const boardResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/desk/board",
    )
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 60_000 })
    const response = await boardResponse
    expect(response.status()).toBe(200)
    expect(await response.json()).toMatchObject({
      schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming",
    })
    await expect(page.getByRole("heading", { name: "Find your matchups." })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("group", { name: "Event context" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Reload published data" })).toBeEnabled({ timeout: 15_000 })
    await page.getByRole("link", { name: /My card/ }).click()
    await expect(page).toHaveURL(/\/card$/)
    await expect(page.getByRole("heading", { name: "Your card." })).toBeVisible()
  })

  test("results analytics tab loads workspace", async ({ page }) => {
    await page.goto("/results?tab=analytics", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    })
    await expect(page.getByTestId("results-page")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId("analytics-workspace")).toBeVisible({ timeout: 30_000 })
  })

  test("system status panels visible", async ({ page }) => {
    await page.goto("/system", { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page.getByTestId("system-page")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId("system-worker-panel")).toBeVisible({ timeout: 30_000 })
  })

  test("track-record redirects to analytics", async ({ page }) => {
    await page.goto("/track-record", { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page).toHaveURL(/tab=analytics/)
    await expect(page.getByTestId("analytics-workspace")).toBeVisible({ timeout: 30_000 })
  })
})
