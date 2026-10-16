import { test, expect } from "@playwright/test"

test.describe("operator terminal core routes", () => {
  test.beforeEach(async ({ page, baseURL }) => {
    if (!baseURL || !["127.0.0.1", "localhost", "[::1]"].includes(new URL(baseURL).hostname)) throw new Error("Browser checks require an isolated local preview.")
    await page.route("**/api/**", route => ["GET", "HEAD", "OPTIONS"].includes(route.request().method()) ? route.continue() : route.fulfill({ status: 405, body: "Browser checks are read-only" }))
    await page.addInitScript(() => {
      localStorage.setItem("golf-model.theme", "dark")
    })
    await page.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
  })

  test("home loads rankings from its local read-only endpoint and preserves the saved card route", async ({ page }) => {
    const boardResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/desk/board",
    )
    await page.goto("/", { waitUntil: "domcontentloaded", timeout: 60_000 })
    const response = await boardResponse
    expect(response.status()).toBe(200)
    expect(await response.json()).toMatchObject({
      schema_version: "operator-read-model/v1", track: "champion", mode: "upcoming",
    })
    await expect(page.getByRole("heading", { name: "Rankings", exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("button", { name: "Upcoming", exact: true })).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByRole("button", { name: "In play", exact: true })).toBeVisible()
    await expect(page.getByRole("region", { name: "Full field rankings" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Reload rankings" })).toBeEnabled({ timeout: 15_000 })
    await page.getByRole("link", { name: /My card/ }).click()
    await expect(page).toHaveURL(/\/card$/)
    await expect(page.getByRole("heading", { name: "Your card." })).toBeVisible()
  })

  test("markets retains event controls and the published market board", async ({ page }) => {
    await page.goto("/markets", { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page.getByRole("heading", { name: "Find your markets." })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("group", { name: "Event context" })).toBeVisible()
    await expect(page.getByRole("button", { name: "Reload published data" })).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByRole("region", { name: "Market board" })).toBeVisible()
  })

  test("published performance JSON and source CSV are served as files, with missing reports returning 404", async ({ page, request }) => {
    const report = await request.get("/reports/performance-2026.json")
    expect(report.status()).toBe(200)
    expect(report.headers()["content-type"]).toContain("application/json")
    expect(await report.json()).toMatchObject({
      schema_version: 1,
      scopes: { "pre_event|dashboard|all": { summary: { decisions: expect.any(Number) } } },
    })
    const csv = await request.get("/reports/season-2026-decisions.csv")
    expect(csv.status()).toBe(200)
    expect(csv.headers()["content-type"]).toContain("text/csv")
    expect(await csv.text()).toMatch(/^decision_id,event_name,event_start,/)
    expect((await request.get("/reports/does-not-exist.json")).status()).toBe(404)
    await page.goto("/performance", { waitUntil: "domcontentloaded", timeout: 60_000 })
    await expect(page.getByRole("heading", { name: "The event record", exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("link", { name: "Download source CSV" })).toHaveAttribute("href", "/reports/season-2026-decisions.csv")
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
