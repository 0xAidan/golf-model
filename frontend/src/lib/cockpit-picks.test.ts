import { describe, expect, it } from "vitest"

import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
  getRawGeneratedMatchups,
  getRawGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import type { PastMarketPredictionRow, PredictionRunResponse } from "@/lib/types"

describe("cockpit pick inventory", () => {
  it("prefers all-books matchup inventory for the raw generated set", () => {
    const run: PredictionRunResponse = {
      status: "ok",
      matchup_bets: [
        {
          pick: "Filtered Pick",
          pick_key: "filtered_pick",
          opponent: "Filtered Opponent",
          opponent_key: "filtered_opponent",
          odds: "-110",
          model_win_prob: 0.55,
          implied_prob: 0.5,
          ev: 0.05,
          ev_pct: "5.0%",
          composite_gap: 1,
          form_gap: 1,
          course_fit_gap: 1,
          reason: "filtered",
        },
      ],
      matchup_bets_all_books: [
        {
          pick: "Raw Pick A",
          pick_key: "raw_pick_a",
          opponent: "Raw Opponent A",
          opponent_key: "raw_opp_a",
          odds: "-110",
          model_win_prob: 0.56,
          implied_prob: 0.5,
          ev: 0.06,
          ev_pct: "6.0%",
          composite_gap: 1,
          form_gap: 1,
          course_fit_gap: 1,
          reason: "raw-a",
        },
        {
          pick: "Raw Pick B",
          pick_key: "raw_pick_b",
          opponent: "Raw Opponent B",
          opponent_key: "raw_opp_b",
          odds: "+105",
          model_win_prob: 0.57,
          implied_prob: 0.48,
          ev: 0.07,
          ev_pct: "7.0%",
          composite_gap: 1,
          form_gap: 1,
          course_fit_gap: 1,
          reason: "raw-b",
        },
      ],
      value_bets: {},
    }

    expect(getRawGeneratedMatchups(run)).toHaveLength(2)
    expect(getRawGeneratedMatchups(run)[0]?.pick).toBe("Raw Pick A")
  })

  it("returns the full generated secondary inventory from value bets", () => {
    const run: PredictionRunResponse = {
      status: "ok",
      value_bets: {
        top10: [
          {
            bet_type: "top10",
            player: "Player A",
            odds: "+250",
            book: "draftkings",
            ev: 0.11,
            is_value: true,
          },
          {
            bet_type: "top10",
            player: "Player B",
            odds: "+300",
            book: "fanduel",
            ev: 0.09,
            is_value: false,
          },
        ],
        top20: [
          {
            bet_type: "top20",
            player: "Player C",
            odds: "+180",
            book: "betmgm",
            ev: 0.08,
            is_value: true,
          },
        ],
      },
    }

    const secondary = getRawGeneratedSecondaryBets(run)

    expect(secondary).toHaveLength(2)
    expect(secondary.map((bet) => bet.player)).toEqual(["Player A", "Player C"])
  })

  it("rebuilds replay matchup and secondary inventory from persisted past market rows", () => {
    const rows: PastMarketPredictionRow[] = [
      {
        snapshot_id: "snap-1",
        event_id: "evt-1",
        section: "live",
        market_family: "matchup",
        market_type: "tournament_matchups",
        player_key: "player_a",
        player_display: "Player A",
        opponent_key: "player_b",
        opponent_display: "Player B",
        odds: "-110",
        book: "bet365",
        ev: 0.11,
        payload: {
          reason: "Replay row",
          tier: "GOOD",
          composite_gap: 1.2,
        },
      },
      {
        snapshot_id: "snap-2",
        event_id: "evt-1",
        section: "live",
        market_family: "placement",
        market_type: "top10",
        player_key: "player_c",
        player_display: "Player C",
        odds: "+250",
        book: "draftkings",
        ev: 0.08,
      },
    ]

    const replayMatchups = buildReplayGeneratedMatchups(rows)
    const replaySecondary = buildReplayGeneratedSecondaryBets(rows)

    expect(replayMatchups).toHaveLength(1)
    expect(replayMatchups[0]?.pick).toBe("Player A")
    expect(replaySecondary).toHaveLength(1)
    expect(replaySecondary[0]).toMatchObject({
      market: "top10",
      player: "Player C",
      ev: 0.08,
    })
  })
})
