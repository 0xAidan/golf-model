/**
 * Continuous red → green heat for scores and SG trajectory (multi-stop RGB, not coarse HSL bands).
 */

type Rgb = readonly [number, number, number]

/** Dense stops so every step is a smooth blend (full perceptual sweep through the warm/cool transition). */
const HEAT_STOPS: readonly { t: number; rgb: Rgb }[] = [
  { t: 0, rgb: [232, 36, 52] },
  { t: 0.08, rgb: [236, 52, 44] },
  { t: 0.16, rgb: [239, 76, 38] },
  { t: 0.24, rgb: [242, 108, 34] },
  { t: 0.32, rgb: [245, 138, 34] },
  { t: 0.4, rgb: [247, 164, 38] },
  { t: 0.48, rgb: [249, 188, 46] },
  { t: 0.52, rgb: [246, 206, 56] },
  { t: 0.58, rgb: [228, 211, 58] },
  { t: 0.64, rgb: [196, 212, 62] },
  { t: 0.7, rgb: [164, 208, 66] },
  { t: 0.76, rgb: [126, 200, 72] },
  { t: 0.82, rgb: [88, 190, 76] },
  { t: 0.88, rgb: [56, 178, 80] },
  { t: 0.94, rgb: [34, 162, 84] },
  { t: 1, rgb: [22, 142, 82] },
]

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x))
}

function rgbToCss(r: number, g: number, b: number): string {
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}

/** Map unit interval → RGB along a smooth red→green spectrum. */
export function heatSpectrumFromUnit(t: number): string {
  const x = clamp01(t)
  let i = 0
  while (i < HEAT_STOPS.length - 1 && HEAT_STOPS[i + 1]!.t < x) i += 1
  const a = HEAT_STOPS[i]!
  const b = HEAT_STOPS[i + 1] ?? a
  const span = b.t - a.t || 1
  const u = (x - a.t) / span
  const r = a.rgb[0] + (b.rgb[0] - a.rgb[0]) * u
  const g = a.rgb[1] + (b.rgb[1] - a.rgb[1]) * u
  const bl = a.rgb[2] + (b.rgb[2] - a.rgb[2]) * u
  return rgbToCss(r, g, bl)
}

/**
 * Horizontal gradient string for meter fills: shifts hue along the bar so reads as a rich sweep
 * rather than a flat swatch.
 */
export function heatSpectrumGradientAlongUnit(
  t: number,
  dir: "ltr" | "rtl",
): string {
  const x = clamp01(t)
  const delta = 0.14
  const c0 = heatSpectrumFromUnit(clamp01(x - delta))
  const c1 = heatSpectrumFromUnit(clamp01(x + delta))
  const angle = dir === "ltr" ? "90deg" : "270deg"
  return `linear-gradient(${angle}, ${c0}, ${c1})`
}

/** @deprecated Use heatSpectrumFromUnit — kept for existing imports. */
export function heatHslFromUnit(t: number): string {
  return heatSpectrumFromUnit(t)
}

export function heatHslFromScore(value: number, max: number): string {
  if (!Number.isFinite(value) || max <= 0) return heatSpectrumFromUnit(0.5)
  return heatSpectrumFromUnit(value / max)
}

export function computeSgTrajectoryBounds(rows: { momentum_trend?: number }[]): { min: number; max: number } {
  const vals = rows
    .map((r) => r.momentum_trend)
    .filter((v): v is number => v != null && Number.isFinite(v))
  if (vals.length === 0) {
    return { min: -45, max: 45 }
  }
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  if (min === max) {
    const pad = Math.abs(min) * 0.25 + 8
    return { min: min - pad, max: max + pad }
  }
  return { min, max }
}

/** Minimum span so tight clusters still traverse most of the spectrum. */
const TRAJECTORY_MIN_SPAN = 34

/** Normalize raw SG trajectory to [0,1] for spectrum lookup. */
export function heatUnitForTrajectory(raw: number, min: number, max: number): number {
  let lo = min
  let hi = max
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return 0.5
  if (hi < lo) [lo, hi] = [hi, lo]
  let span = hi - lo
  if (span < 1e-9) return 0.5
  if (span < TRAJECTORY_MIN_SPAN) {
    const mid = (hi + lo) / 2
    lo = mid - TRAJECTORY_MIN_SPAN / 2
    hi = mid + TRAJECTORY_MIN_SPAN / 2
    span = TRAJECTORY_MIN_SPAN
  }
  return clamp01((raw - lo) / span)
}

/**
 * Map bucket to a nominal raw trend when API omits momentum_trend (rare).
 */
export function nominalTrajectoryFromDirection(direction?: string): number | undefined {
  const n = (
    {
      hot: 35,
      warming: 12,
      cooling: -12,
      cold: -35,
    } as Record<string, number>
  )[direction ?? ""]
  return n
}
