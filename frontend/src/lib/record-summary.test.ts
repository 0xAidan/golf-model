import { describe, expect, it } from "vitest"

import { buildGradingRecordSummary } from "@/lib/record-summary"
import type { GradedTournamentSummary } from "@/lib/types"

describe("buildGradingRecordSummary", () => {
  it("prefers API-provided 1u market summaries when available", () => {
    const gradingHistory: GradedTournamentSummary[] = [
      {
        name: "RBC Heritage",
        graded_pick_count: 99,
        hits: 99,
        total_profit: 99,
      },
    ]

    const summary = buildGradingRecordSummary(gradingHistory, {
      combined: { picks: 6, wins: 2, losses: 2, pushes: 2, profit: 2.91, hit_rate: 0.333 },
      matchups: { picks: 3, wins: 1, losses: 1, pushes: 1, profit: -0.09, hit_rate: 0.333 },
      outrights: { picks: 3, wins: 1, losses: 1, pushes: 1, profit: 3, hit_rate: 0.333 },
    })

    expect(summary.combined.profit).toBe(2.91)
    expect(summary.combined.recordLabel).toBe("2-2-2")
    expect(summary.matchups.profit).toBe(-0.09)
    expect(summary.outrights.recordLabel).toBe("1-1-1")
  })

  it("falls back to graded picks split by bet type", () => {
    const gradingHistory: GradedTournamentSummary[] = [
      {
        name: "Fallback Event",
        picks: [
          { player_display: "Matchup Win", opponent_display: "Opponent", bet_type: "matchup", hit: 1, profit: 0.91 },
          { player_display: "Matchup Loss", opponent_display: "Opponent", bet_type: "matchup", hit: 0, profit: -1 },
          { player_display: "Top 5 Push", bet_type: "top5", hit: 0, profit: 0 },
          { player_display: "Outright Win", bet_type: "outright", hit: 1, profit: 4 },
        ],
      },
    ]

    const summary = buildGradingRecordSummary(gradingHistory)

    expect(summary.combined).toMatchObject({ picks: 4, wins: 2, losses: 1, pushes: 1, profit: 3.91 })
    expect(summary.matchups).toMatchObject({ picks: 2, wins: 1, losses: 1, pushes: 0, profit: -0.09 })
    expect(summary.outrights).toMatchObject({ picks: 2, wins: 1, losses: 0, pushes: 1, profit: 4 })
  })
})
