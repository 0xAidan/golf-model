import { describe, expect, it } from "vitest"

import type { CompositePlayer } from "@/lib/types"

import { computeFieldPercentile, computePlayerFieldPercentiles } from "./field-percentiles"

const makePlayer = (overrides: Partial<CompositePlayer> & { player_key: string }): CompositePlayer =>
  ({
    player_display: overrides.player_key,
    rank: 10,
    composite: 50,
    form: 50,
    course_fit: 50,
    momentum: 0,
    ...overrides,
  }) as CompositePlayer

describe("field-percentiles", () => {
  it("computes percentile with higher-is-better", () => {
    expect(computeFieldPercentile(80, [10, 20, 30, 40, 50, 60, 70], true)).toBe(100)
    expect(computeFieldPercentile(5, [10, 20, 30], true)).toBe(0)
  })

  it("computes player field percentiles from composite board", () => {
    const field = [
      makePlayer({ player_key: "a", composite: 60, form: 70, rank: 1 }),
      makePlayer({ player_key: "b", composite: 50, form: 50, rank: 2 }),
      makePlayer({ player_key: "c", composite: 40, form: 30, rank: 3 }),
    ]
    const pct = computePlayerFieldPercentiles(field[0], field)
    expect(pct.composite).toBe(67)
    expect(pct.form).toBe(67)
    expect(pct.rank).toBe(67)
  })
})
