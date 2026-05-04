/**
 * Red → green heat scales for 0–max scores (e.g. Form) and field-relative SG trajectory.
 */

export function heatHslFromUnit(t: number): string {
  const x = Math.min(1, Math.max(0, t))
  // 0 = red, ~0.5 = yellow-green, 1 = green
  const hue = x * 118
  return `hsl(${hue}, 72%, 46%)`
}

export function heatHslFromScore(value: number, max: number): string {
  if (!Number.isFinite(value) || max <= 0) return heatHslFromUnit(0.5)
  return heatHslFromUnit(value / max)
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

/** Normalize raw SG trajectory to a heat unit interval using field min/max. */
export function heatUnitForTrajectory(raw: number, min: number, max: number): number {
  const span = max - min
  if (!Number.isFinite(span) || span <= 0) return 0.5
  return (raw - min) / span
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
