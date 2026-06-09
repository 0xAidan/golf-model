import { describe, expect, it } from "vitest"

import type { FlattenedSecondaryBet, MatchupBet } from "@/lib/types"

import { filterLinkedPicks } from "./linked-picks"

describe("filterLinkedPicks", () => {
  it("returns empty bundle for missing key", () => {
    expect(filterLinkedPicks("", [], [])).toEqual({
      matchups: [],
      secondary: [],
      totalCount: 0,
    })
  })

  it("filters matchups and secondary bets by player key", () => {
    const matchups = [
      {
        pick_key: "a",
        opponent_key: "b",
        pick: "A",
        opponent: "B",
        odds: "+100",
        ev: 0.05,
        ev_pct: "5%",
        model_win_prob: 0.5,
        implied_prob: 0.45,
        composite_gap: 1,
        form_gap: 1,
        course_fit_gap: 1,
        reason: "test",
      },
    ] as MatchupBet[]

    const secondary = [
      { market: "top20", player_key: "a", player: "A", odds: "+200", ev: 0.03 },
    ] as FlattenedSecondaryBet[]

    const result = filterLinkedPicks("a", matchups, secondary)
    expect(result.totalCount).toBe(2)
    expect(result.matchups).toHaveLength(1)
    expect(result.secondary).toHaveLength(1)
  })
})
