import { describe, expect, it } from "vitest"

import {
  computeComponentDeltaRows,
  computeComponentDriverSummary,
  computeMatchupDiffRows,
  computeMatchupOverlap,
  computeRankDeltas,
  computeRankScatterPoints,
  matchupKey,
  median,
} from "@/components/compare/compare-utils"
import type { FieldBoardPlayer, LiveRankingRow, MatchupBet } from "@/lib/types"

const ranking = (
  rank: number,
  key: string,
  player: string,
  composite: number,
): LiveRankingRow => ({
  rank,
  player_key: key,
  player,
  composite,
  course_fit: composite * 0.1,
  form: composite * 0.2,
  momentum: composite * 0.01,
})

const bet = (pickKey: string, oppKey: string, ev: number): MatchupBet => ({
  pick: pickKey.toUpperCase(),
  pick_key: pickKey,
  opponent: oppKey.toUpperCase(),
  opponent_key: oppKey,
  odds: "-110",
  model_win_prob: 0.55,
  implied_prob: 0.52,
  ev,
  ev_pct: "6%",
  composite_gap: 1,
  form_gap: 0,
  course_fit_gap: 0,
  reason: "test",
})

describe("compare-utils", () => {
  it("matchupKey normalizes case", () => {
    expect(matchupKey({ pick_key: "A", opponent_key: "B" })).toBe("a|b")
  })

  it("median handles even and odd lengths", () => {
    expect(median([1, 3, 5])).toBe(3)
    expect(median([1, 2, 3, 4])).toBe(2.5)
    expect(median([])).toBeNull()
  })

  it("computeRankDeltas sorts by absolute delta", () => {
    const champ = [ranking(1, "a", "A", 80), ranking(2, "b", "B", 78)]
    const chall = [ranking(5, "a", "A", 70), ranking(1, "b", "B", 82)]
    const rows = computeRankDeltas(champ, chall)
    expect(rows[0].playerKey).toBe("a")
    expect(rows[0].delta).toBe(-4)
  })

  it("computeRankScatterPoints filters to both-ranked players", () => {
    const players: FieldBoardPlayer[] = [
      {
        player_key: "a",
        player: "A",
        champion_rank: 1,
        challenger_rank: 5,
        rank_delta: -4,
        composite: 80,
        course_fit: 1,
        form: 2,
        momentum: 0.1,
        matchup_count: 0,
        in_positive_ev: false,
        has_sg: false,
      },
      {
        player_key: "b",
        player: "B",
        champion_rank: null,
        challenger_rank: 1,
        rank_delta: null,
        composite: null,
        course_fit: null,
        form: null,
        momentum: null,
        matchup_count: 0,
        in_positive_ev: false,
        has_sg: false,
      },
    ]
    expect(computeRankScatterPoints(players)).toHaveLength(1)
  })

  it("computeComponentDeltaRows joins both tracks", () => {
    const champ = [ranking(1, "a", "A", 80)]
    const chall = [ranking(5, "a", "A", 70)]
    const rows = computeComponentDeltaRows(champ, chall)
    expect(rows).toHaveLength(1)
    expect(rows[0].compositeDelta).toBe(10)
    expect(rows[0].rankDelta).toBe(-4)
  })

  it("computeComponentDriverSummary averages abs deltas above threshold", () => {
    const rows = computeComponentDeltaRows(
      [ranking(1, "a", "A", 80), ranking(10, "b", "B", 60)],
      [ranking(5, "a", "A", 70), ranking(10, "b", "B", 60)],
    )
    const summary = computeComponentDriverSummary(rows, 3)
    expect(summary.sampleSize).toBe(1)
    expect(summary.composite).toBe(10)
  })

  it("computeMatchupOverlap buckets picks", () => {
    const overlap = computeMatchupOverlap([bet("a", "b", 0.1)], [bet("c", "d", 0.2)])
    expect(overlap.both).toHaveLength(0)
    expect(overlap.championOnly).toHaveLength(1)
    expect(overlap.challengerOnly).toHaveLength(1)
  })

  it("computeMatchupDiffRows joins EV and prob for overlapping keys", () => {
    const champBet = bet("a", "b", 0.06)
    const challBet = { ...bet("a", "b", 0.1), model_win_prob: 0.6 }
    const rows = computeMatchupDiffRows([champBet], [challBet])
    expect(rows).toHaveLength(1)
    expect(rows[0].bucket).toBe("both")
    expect(rows[0].evDelta).toBeCloseTo(0.04)
    expect(rows[0].championProb).toBe(0.55)
    expect(rows[0].challengerProb).toBe(0.6)
  })
})
