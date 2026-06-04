#!/usr/bin/env node
/**
 * Playwright screenshot matrix for UI overhaul verification.
 * Requires: npm install -D playwright && npx playwright install chromium
 */
import { chromium } from "playwright"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, "../..")
const outDir = path.join(repoRoot, "docs/screenshots/ui-overhaul-v2")
const baseUrl = process.env.SCREENSHOT_BASE_URL ?? "http://127.0.0.1:8000"

const routes = [
  { name: "dashboard", hash: "#/" },
  { name: "picks", hash: "#/matchups" },
  { name: "players", hash: "#/players" },
  { name: "grading", hash: "#/grading" },
  { name: "track-record", hash: "#/track-record" },
  { name: "legacy-model", hash: "#/research/legacy-model" },
  { name: "champion-challenger", hash: "#/research/champion-challenger" },
  { name: "diagnostics", hash: "#/research/diagnostics" },
]

const viewports = [
  { label: "375", width: 375, height: 812 },
  { label: "1280", width: 1280, height: 900 },
]

const themes = ["dark", "light"]

async function main() {
  await mkdir(outDir, { recursive: true })
  const browser = await chromium.launch()
  const index = []

  for (const theme of themes) {
    for (const vp of viewports) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        colorScheme: theme === "dark" ? "dark" : "light",
      })
      await context.addInitScript((t) => {
        localStorage.setItem("golf-model.theme", t)
      }, theme)
      const page = await context.newPage()
      for (const route of routes) {
        const url = `${baseUrl.replace(/\/$/, "")}${route.hash.startsWith("#") ? route.hash : `#${route.hash}`}`
        const fileName = `${route.name}-${vp.label}-${theme}.png`
        const file = path.join(outDir, fileName)
        try {
          await page.goto(url, { waitUntil: "load", timeout: 45_000 })
          await page.waitForTimeout(1200)
          await page.screenshot({ path: file, fullPage: true })
          index.push({ route: route.name, viewport: vp.label, theme, file: fileName })
          console.log("wrote", file)
        } catch (err) {
          console.warn("skip", url, err instanceof Error ? err.message : err)
        }
      }
      await context.close()
    }
  }
  await browser.close()

  await writeFile(
    path.join(outDir, "README.md"),
    `# UI Overhaul V2 screenshot matrix\n\nCaptured: ${new Date().toISOString()}\n\nTotal: ${index.length} images\n\n| Route | 375 dark | 375 light | 1280 dark | 1280 light |\n|-------|----------|-----------|-----------|------------|\n${routes.map((r) => `| ${r.name} | ${index.some((i) => i.route === r.name && i.viewport === "375" && i.theme === "dark") ? "yes" : "—"} | ${index.some((i) => i.route === r.name && i.viewport === "375" && i.theme === "light") ? "yes" : "—"} | ${index.some((i) => i.route === r.name && i.viewport === "1280" && i.theme === "dark") ? "yes" : "—"} | ${index.some((i) => i.route === r.name && i.viewport === "1280" && i.theme === "light") ? "yes" : "—"} |`).join("\n")}\n`,
  )
  console.log(`Done: ${index.length} screenshots`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
