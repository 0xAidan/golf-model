#!/usr/bin/env node
/**
 * Pixel-compare PR screenshots against a committed baseline directory.
 * Skips pairs when baseline PNG is missing. Fails when diff ratio exceeds threshold.
 *
 * Baseline dir is configurable via VISUAL_BASELINE_DIR (relative to repo root or
 * absolute). It defaults to the engine-scale-v1 baseline; the legacy
 * ui-overhaul-v3 baseline predates the PR #145 product rebuild and is retained
 * for history only. The comparison skips gracefully when the baseline dir does
 * not yet contain PNGs, so CI stays green until a real-data baseline is captured.
 */
import { readFile, readdir, access } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { PNG } from "pngjs"
import pixelmatch from "pixelmatch"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, "../..")
const resolveFromRoot = (p) => (path.isAbsolute(p) ? p : path.join(repoRoot, p))
const baselineDir = resolveFromRoot(
  process.env.VISUAL_BASELINE_DIR ?? "docs/screenshots/engine-scale-v1",
)
const candidateDir =
  process.env.VISUAL_CANDIDATE_DIR ??
  path.join(repoRoot, "docs/screenshots/engine-scale-v1-pr")

const MAX_DIFF_RATIO = Number(process.env.VISUAL_MAX_DIFF_RATIO ?? "0.08")
const ROUTES_FILTER = process.env.VISUAL_ROUTES?.split(",").filter(Boolean)

async function fileExists(p) {
  try {
    await access(p)
    return true
  } catch {
    return false
  }
}

function loadPng(filePath) {
  const data = readFile(filePath).then((buf) => PNG.sync.read(buf))
  return data
}

async function main() {
  if (!(await fileExists(baselineDir))) {
    console.warn(`Baseline directory missing: ${baselineDir} — skipping visual diff`)
    return
  }
  if (!(await fileExists(candidateDir))) {
    console.warn(`Candidate directory missing: ${candidateDir} — skipping visual diff`)
    return
  }

  const baselineFiles = (await readdir(baselineDir)).filter((n) => n.endsWith(".png"))
  const candidates = (await readdir(candidateDir)).filter((n) => n.endsWith(".png"))
  const names = baselineFiles.filter((name) => candidates.includes(name))

  if (names.length === 0) {
    console.warn("No overlapping PNG pairs between baseline and candidate — skipping")
    return
  }

  let failures = 0
  let compared = 0

  for (const name of names) {
    const routePrefix = name.split("-")[0]
    if (ROUTES_FILTER?.length && !ROUTES_FILTER.some((r) => name.startsWith(r))) {
      continue
    }

    const baselinePath = path.join(baselineDir, name)
    const candidatePath = path.join(candidateDir, name)
    const [img1, img2] = await Promise.all([loadPng(baselinePath), loadPng(candidatePath)])

    if (img1.width !== img2.width || img1.height !== img2.height) {
      console.error(`${name}: size mismatch ${img1.width}x${img1.height} vs ${img2.width}x${img2.height}`)
      failures += 1
      continue
    }

    const { width, height } = img1
    const diff = new PNG({ width, height })
    const diffPixels = pixelmatch(img1.data, img2.data, diff.data, width, height, {
      threshold: 0.12,
    })
    const ratio = diffPixels / (width * height)
    compared += 1
    console.log(`${name}: ${(ratio * 100).toFixed(2)}% pixels differ`)

    if (ratio > MAX_DIFF_RATIO) {
      failures += 1
      const out = path.join(candidateDir, `_diff_${name}`)
      const { writeFile } = await import("node:fs/promises")
      await writeFile(out, PNG.sync.write(diff))
      console.error(`  FAIL (max ${(MAX_DIFF_RATIO * 100).toFixed(0)}%) — wrote ${out}`)
    }
  }

  console.log(`Compared ${compared} image(s); failures: ${failures}`)
  if (failures > 0) process.exit(1)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
