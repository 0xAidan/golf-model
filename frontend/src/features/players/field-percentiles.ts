import type { CompositePlayer } from "@/lib/types"

import type { FieldPercentileMap } from "./player-workspace-types"

/** Percentile 0–100 where higher = better for rank-oriented metrics (lower rank = higher percentile). */
export const computeFieldPercentile = (
  value: number | null | undefined,
  fieldValues: number[],
  higherIsBetter = true,
): number | null => {
  if (value == null || !Number.isFinite(value) || fieldValues.length === 0) return null
  const sorted = [...fieldValues].filter((v) => Number.isFinite(v)).sort((a, b) => a - b)
  if (!sorted.length) return null
  const below = sorted.filter((v) => (higherIsBetter ? v < value : v > value)).length
  return Math.round((below / sorted.length) * 100)
}

export const computePlayerFieldPercentiles = (
  player: CompositePlayer | undefined,
  field: CompositePlayer[],
): FieldPercentileMap => {
  if (!player || !field.length) {
    return {}
  }

  const composites = field.map((p) => p.composite)
  const forms = field.map((p) => p.form)
  const courseFits = field.map((p) => p.course_fit)
  const trajectories = field.map((p) => p.momentum_trend ?? 0)
  const ranks = field.map((p) => p.rank)

  return {
    composite: computeFieldPercentile(player.composite, composites, true),
    form: computeFieldPercentile(player.form, forms, true),
    course_fit: computeFieldPercentile(player.course_fit, courseFits, true),
    momentum_trend: computeFieldPercentile(player.momentum_trend ?? 0, trajectories, true),
    rank: computeFieldPercentile(player.rank, ranks, false),
  }
}

export const buildModelFieldValues = (
  field: CompositePlayer[],
): {
  composite: number[]
  form: number[]
  course_fit: number[]
  momentum_trend: number[]
} => ({
  composite: field.map((p) => p.composite),
  form: field.map((p) => p.form),
  course_fit: field.map((p) => p.course_fit),
  momentum_trend: field.map((p) => p.momentum_trend ?? 0),
})
