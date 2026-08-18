#!/usr/bin/env node

/**
 * Operator baseline schema guard / capture helper.
 *
 * Capture workflow:
 *   1. Point BASE_URL at a non-production build (never mutate production).
 *   2. Capture five cold and five warm runs per active route.
 *   3. Write evidence-backed measurements into
 *      docs/frontend-recovery/baseline.json (no null metric values).
 *
 * Modes:
 *   --check-schema   validate committed baseline.json (default)
 *   --help           print this help
 *
 * This script intentionally performs no production calls and makes no
 * destructive requests. Full Playwright capture can be layered later when a
 * safe local URL is supplied; without one, schema validation is the gate.
 */

import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import path from "node:path"

export const REQUIRED_METRIC_KEYS = [
  "routes_measured",
  "cold_runs_per_route",
  "warm_runs_per_route",
  "request_count_p50",
  "compressed_bytes_p50",
  "ttfb_ms_p50",
  "first_useful_content_ms_p50",
  "route_ready_ms_p50",
  "cls_p50",
  "longest_task_ms_p50",
  "console_errors_total",
  "failed_resources_total",
  "mobile_viewport_width",
  "desktop_viewport_width",
  "wide_viewport_width",
]

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const baselinePath = path.resolve(
  scriptDirectory,
  "../../docs/frontend-recovery/baseline.json",
)

const hasRequiredMetricValue = (metrics, key) =>
  Object.prototype.hasOwnProperty.call(metrics, key) && metrics[key] !== null

const loadBaseline = async () => JSON.parse(await readFile(baselinePath, "utf8"))

export const checkSchema = async () => {
  const baseline = await loadBaseline()
  const requiredMetricKeys = baseline.required_metric_keys

  if (!Array.isArray(requiredMetricKeys)) {
    throw new Error("baseline.json must include a required_metric_keys array.")
  }

  const omittedScriptKeys = REQUIRED_METRIC_KEYS.filter(
    (key) => !requiredMetricKeys.includes(key),
  )
  const unexpectedBaselineKeys = requiredMetricKeys.filter(
    (key) => !REQUIRED_METRIC_KEYS.includes(key),
  )

  if (omittedScriptKeys.length > 0 || unexpectedBaselineKeys.length > 0) {
    throw new Error(
      `required_metric_keys must match the script contract. Missing: ${
        omittedScriptKeys.join(", ") || "none"
      }. Unexpected: ${unexpectedBaselineKeys.join(", ") || "none"}.`,
    )
  }

  if (!baseline.metrics || typeof baseline.metrics !== "object") {
    throw new Error("baseline.json must include a metrics object.")
  }

  const invalidMetrics = REQUIRED_METRIC_KEYS.filter(
    (key) => !hasRequiredMetricValue(baseline.metrics, key),
  )

  if (invalidMetrics.length > 0) {
    throw new Error(
      `baseline.json has missing or null required metrics: ${invalidMetrics.join(", ")}.`,
    )
  }

  console.log(
    `Baseline schema valid (${REQUIRED_METRIC_KEYS.length} required metrics; status: ${baseline.status ?? "unknown"}).`,
  )
  return baseline
}

const printHelp = () => {
  console.log(`Usage: node frontend/scripts/capture-operator-baseline.mjs [--check-schema|--help]

--check-schema   Validate docs/frontend-recovery/baseline.json (default)
--help           Show help

Capture notes:
  Provide a safe local BASE_URL when adding Playwright capture.
  Never point this at production with mutation-enabled flows.
  Do not write null placeholders for required metrics.
`)
}

const main = async () => {
  const args = new Set(process.argv.slice(2))
  if (args.has("--help") || args.has("-h")) {
    printHelp()
    return
  }
  if (args.size === 0 || args.has("--check-schema")) {
    await checkSchema()
    return
  }
  throw new Error(`Unknown arguments: ${[...args].join(" ")}. Use --help.`)
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("capture-operator-baseline.mjs")) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  })
}
