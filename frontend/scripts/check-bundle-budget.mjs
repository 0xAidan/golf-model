#!/usr/bin/env node
/**
 * Fail when the main entry chunk gzip size grows more than 5% vs performance-baseline.json.
 */
import { readFile, readdir } from "node:fs/promises"
import { createReadStream } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { createGzip } from "node:zlib"
import { pipeline } from "node:stream/promises"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, "../..")
const distAssets = path.join(repoRoot, "frontend/dist/assets")
const baselinePath = path.join(repoRoot, "docs/frontend-overhaul/performance-baseline.json")

async function gzipSize(filePath) {
  const gzip = createGzip()
  let bytes = 0
  gzip.on("data", (chunk) => {
    bytes += chunk.length
  })
  await pipeline(createReadStream(filePath), gzip)
  return bytes
}

async function findMainChunk() {
  const files = await readdir(distAssets)
  const candidates = files.filter((name) => /^index-[^/]+\.js$/.test(name) && !name.includes(".map"))
  if (candidates.length === 0) {
    throw new Error(`No index-*.js in ${distAssets} — run npm run build first`)
  }
  let best = candidates[0]
  let bestSize = 0
  for (const name of candidates) {
    const full = path.join(distAssets, name)
    const { size } = await import("node:fs/promises").then((fs) => fs.stat(full))
    if (size > bestSize) {
      bestSize = size
      best = name
    }
  }
  return { name: best, path: path.join(distAssets, best), bytes: bestSize }
}

async function main() {
  const baselineRaw = await readFile(baselinePath, "utf8")
  const baseline = JSON.parse(baselineRaw)
  const limitRatio = baseline.budget?.mainChunkGrowthMaxRatio ?? 1.05
  const baselineGzip =
    baseline.after?.mainChunkGzipBytes ?? baseline.before?.mainChunkGzipBytes
  if (!baselineGzip) {
    throw new Error("performance-baseline.json missing mainChunkGzipBytes")
  }

  const chunk = await findMainChunk()
  const gzipBytes = await gzipSize(chunk.path)
  const maxAllowed = Math.ceil(baselineGzip * limitRatio)

  console.log(`Main chunk: ${chunk.name}`)
  console.log(`Raw: ${chunk.bytes} bytes | gzip: ${gzipBytes} bytes`)
  console.log(`Baseline gzip: ${baselineGzip} | max allowed (+${((limitRatio - 1) * 100).toFixed(0)}%): ${maxAllowed}`)

  if (gzipBytes > maxAllowed) {
    console.error(
      `Bundle budget exceeded: ${gzipBytes} > ${maxAllowed} (${((gzipBytes / baselineGzip - 1) * 100).toFixed(1)}% vs baseline)`,
    )
    process.exit(1)
  }

  console.log("Bundle budget OK.")
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
