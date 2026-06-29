import { describe, expect, it } from "vitest"

import { applyGradedPicksToMatchups } from "@/lib/apply-graded-picks"
import type { MatchupBet, TrackRecordPick } from "@/lib/types"

const baseMatchup = (): MatchupBet => ({
  pick: "Patrick Rodgers",
  pick_key: "wrong_pick_key",
  opponent: "Sungjae Im",
  opponent_key: "wrong_opp_key",
  odds: "-110",
  model_win_prob: 0.55,
  implied_prob: 0.52,
  ev: 0.03,
  ev_pct: "3.0%",
  composite_gap: 0,
  form_gap: 0,
  course_fit_gap: 0,
  reason: "test",
})

const gradedPick = (over: Partial<TrackRecordPick> = {}): TrackRecordPick => ({
  bet_type: "matchup",
  player_key: "patrick_rodgers",
  player_display: "Patrick Rodgers",
  opponent_key: "sungjae_im",
  opponent_display: "Sungjae Im",
  hit: 1,
  profit: 0.9,
  outcome: "win",
  ev: 0.03,
  ...over,
})

describe("applyGradedPicksToMatchups", () => {
  it("merges graded outcomes when replay keys differ but display names match", () => {
    const merged = applyGradedPicksToMatchups([baseMatchup()], [gradedPick()])
    expect(merged[0]?.graded_result).toBe("win")
  })

  it("respects market_type when matching graded inventory", () => {
    const matchup = { ...baseMatchup(), market_type: "round_matchups" }
    const merged = applyGradedPicksToMatchups(
      [matchup],
      [gradedPick({ market_type: "tournament_matchups" })],
    )
    expect(merged[0]?.graded_result).toBeUndefined()
  })
})
