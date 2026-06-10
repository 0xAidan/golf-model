#!/usr/bin/env node
/**
 * Playwright screenshot matrix for UI overhaul verification.
 * Requires: npm install -D playwright && npx playwright install chromium
 */
import { chromium } from "playwright"
import { mkdir, readdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, "../..")
const matrixVersion = process.env.SCREENSHOT_MATRIX_VERSION ?? "v2"
// SCREENSHOT_OUT_DIR (relative to repo root or absolute) overrides the default
// docs/screenshots/ui-overhaul-<version> path so the engine-scale baseline can
// live under docs/screenshots/engine-scale-v1 without renaming historic matrices.
const outDir = process.env.SCREENSHOT_OUT_DIR
  ? (path.isAbsolute(process.env.SCREENSHOT_OUT_DIR)
      ? process.env.SCREENSHOT_OUT_DIR
      : path.join(repoRoot, process.env.SCREENSHOT_OUT_DIR))
  : path.join(repoRoot, `docs/screenshots/ui-overhaul-${matrixVersion}`)
const includeWideViewport = matrixVersion === "v3" || /engine-scale/i.test(matrixVersion)
const baseUrl = process.env.SCREENSHOT_BASE_URL ?? "http://127.0.0.1:8000"

const routes = [
  { name: "dashboard", hash: "#/" },
  { name: "picks", hash: "#/matchups" },
  { name: "players", hash: "#/players" },
  { name: "lab", hash: "#/lab" },
  { name: "lab-picks", hash: "#/lab/picks" },
  { name: "grading", hash: "#/grading" },
  { name: "track-record", hash: "#/track-record" },
  { name: "legacy-model", hash: "#/research/legacy-model" },
  { name: "champion-challenger", hash: "#/research/champion-challenger" },
  { name: "diagnostics", hash: "#/research/diagnostics" },
]

const viewports = [
  { label: "375", width: 375, height: 812 },
  { label: "1280", width: 1280, height: 900 },
  ...(includeWideViewport
    ? [{ label: "1920", width: 1920, height: 1080 }]
    : []),
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
      // Block legacy CDN fonts only — allow self-hosted /fonts/*.woff2
      await context.route(/fontshare|fonts\.googleapis|fonts\.gstatic/i, (route) => route.abort())
      const page = await context.newPage()
      for (const route of routes) {
        const url = `${baseUrl.replace(/\/$/, "")}${route.hash.startsWith("#") ? route.hash : `#${route.hash}`}`
        const fileName = `${route.name}-${vp.label}-${theme}.png`
        const file = path.join(outDir, fileName)
        try {
          await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45_000 })
          await page.waitForTimeout(1200)
          await Promise.race([
            page.evaluate(() => document.fonts?.ready),
            page.waitForTimeout(2500),
          ])
          await page.screenshot({
            path: file,
            fullPage: true,
            timeout: 15_000,
            animations: "disabled",
          })
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

  const pngFiles = (await readdir(outDir)).filter((name) => name.endsWith(".png"))
  const hasShot = (route, viewport, theme) =>
    pngFiles.includes(`${route}-${viewport}-${theme}.png`)

  await writeFile(
    path.join(outDir, "README.md"),
    `# UI Overhaul ${matrixVersion.toUpperCase()} screenshot matrix\n\nCaptured: ${new Date().toISOString()}\n\nTotal: ${pngFiles.length} images on disk (${index.length} captured this run)\n\n| Route | 375 dark | 375 light | 1280 dark | 1280 light | 1920 dark | 1920 light |\n|-------|----------|-----------|-----------|------------|-----------|------------|\n${routes.map((r) => `| ${r.name} | ${hasShot(r.name, "375", "dark") ? "yes" : "—"} | ${hasShot(r.name, "375", "light") ? "yes" : "—"} | ${hasShot(r.name, "1280", "dark") ? "yes" : "—"} | ${hasShot(r.name, "1280", "light") ? "yes" : "—"} | ${hasShot(r.name, "1920", "dark") ? "yes" : "—"} | ${hasShot(r.name, "1920", "light") ? "yes" : "—"} |`).join("\n")}\n`,
  )
  console.log(`Done: ${index.length} screenshots`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
