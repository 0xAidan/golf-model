import { describe, expect, it } from "vitest"

import { gradedPicksToMatchups, gradedPicksToSecondaryBets } from "@/lib/graded-picks-display"
import type { TrackRecordPick } from "@/lib/types"

const pick = (overrides: Partial<TrackRecordPick>): TrackRecordPick => ({
  player_display: "Player",
  hit: 0,
  profit: -1,
  ...overrides,
})

describe("gradedPicksToMatchups", () => {
  it("maps graded matchup picks with outcomes", () => {
    const rows = gradedPicksToMatchups([
      pick({
        bet_type: "matchup",
        player_display: "Player A",
        player_key: "player_a",
        opponent_display: "Player B",
        opponent_key: "player_b",
        market_odds: "+120",
        ev: 0.08,
        outcome: "win",
      }),
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0]?.graded_result).toBe("win")
    expect(rows[0]?.odds).toBe("+120")
  })
})

describe("gradedPicksToSecondaryBets", () => {
  it("maps non-matchup graded picks", () => {
    const rows = gradedPicksToSecondaryBets([
      pick({
        bet_type: "top10",
        player_display: "Player C",
        player_key: "player_c",
        market_odds: "+650",
        ev: 0.05,
      }),
      pick({
        bet_type: "matchup",
        ev: 0.04,
      }),
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0]?.market).toBe("top10")
  })
})
