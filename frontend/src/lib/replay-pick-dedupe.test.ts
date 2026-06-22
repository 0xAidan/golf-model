import { describe, expect, it } from "vitest"

import { applyGradedPicksToMatchups } from "@/lib/apply-graded-picks"
import { dedupeReplayMatchups } from "@/lib/replay-pick-dedupe"
import { buildEventGradingRecordSummary, buildPastReplayRecordSummary } from "@/lib/record-summary"
import type { MatchupBet, TrackRecordPick } from "@/lib/types"

const matchup = (overrides: Partial<MatchupBet>): MatchupBet => ({
  pick: "Player A",
  pick_key: "player_a",
  opponent: "Player B",
  opponent_key: "player_b",
  odds: "-110",
  model_win_prob: 0.55,
  implied_prob: 0.52,
  ev: 0.05,
  ev_pct: "5.0%",
  composite_gap: 1,
  form_gap: 1,
  course_fit_gap: 1,
  reason: "test",
  ...overrides,
})

describe("dedupeReplayMatchups", () => {
  it("collapses duplicate matchup identities and keeps best odds", () => {
    const rows = [
      matchup({ odds: "-110", book: "fd" }),
      matchup({ odds: "+120", book: "dk" }),
      matchup({ odds: "-105", book: "pinnacle" }),
    ]
    const deduped = dedupeReplayMatchups(rows)
    expect(deduped).toHaveLength(1)
    expect(deduped[0]?.odds).toBe("+120")
  })

  it("ignores non-positive EV rows", () => {
    const deduped = dedupeReplayMatchups([
      matchup({ ev: 0, odds: "+500" }),
      matchup({ ev: 0.01, odds: "-110" }),
    ])
    expect(deduped).toHaveLength(1)
    expect(deduped[0]?.odds).toBe("-110")
  })
})

describe("buildEventGradingRecordSummary", () => {
  it("uses event market_stats instead of season totals", () => {
    const summary = buildEventGradingRecordSummary({
      name: "U.S. Open",
      event_id: "26",
      market_stats: {
        combined: { picks: 20, wins: 6, losses: 14, pushes: 0, profit: 27.3, hit_rate: 0.3 },
        matchups: { picks: 8, wins: 3, losses: 5, pushes: 0, profit: 4.1, hit_rate: 0.375 },
        outrights: { picks: 12, wins: 3, losses: 9, pushes: 0, profit: 23.2, hit_rate: 0.25 },
      },
    })
    expect(summary.combined.profit).toBe(27.3)
    expect(summary.combined.picks).toBe(20)
  })
})

describe("applyGradedPicksToMatchups", () => {
  it("merges stored backend outcomes onto replay rows", () => {
    const graded: TrackRecordPick[] = [
      {
        id: 1,
        bet_type: "matchup",
        player_key: "player_a",
        opponent_key: "player_b",
        player_display: "Player A",
        opponent_display: "Player B",
        hit: 1,
        profit: 0.9,
        outcome: "win",
      },
    ]
    const merged = applyGradedPicksToMatchups([matchup({})], graded)
    expect(merged[0]?.graded_result).toBe("win")
  })
})

describe("buildPastReplayRecordSummary dedupe", () => {
  it("does not double-count duplicate replay rows", () => {
    const board = [
      { rank: 1, player: "Player A", player_key: "player_a", finish_state: "T3" },
      { rank: 2, player: "Player B", player_key: "player_b", finish_state: "T10" },
    ]
    const summary = buildPastReplayRecordSummary(
      [matchup({ odds: "-110" }), matchup({ odds: "+120" })],
      [],
      board,
    )
    expect(summary.matchups.picks).toBe(1)
    expect(summary.matchups.wins).toBe(1)
    expect(summary.matchups.profit).toBeCloseTo(1.2, 2)
  })
})
