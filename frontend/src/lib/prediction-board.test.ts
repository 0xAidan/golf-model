import { describe, expect, it } from "vitest"

import { buildHydratedPredictionRun, buildPredictionRunFromSection, flattenSecondaryBets } from "@/lib/prediction-board"
import type { LiveRefreshSnapshot } from "@/lib/types"

describe("buildHydratedPredictionRun", () => {
  it("preserves enriched ranking fields from snapshot rows", () => {
    const snapshot: LiveRefreshSnapshot = {
      live_tournament: {
        event_name: "Masters Tournament",
        course_name: "Augusta National",
        field_size: 88,
        tournament_id: 9,
        course_num: 10,
        rankings: [
          {
            rank: 1,
            player_key: "jon_rahm",
            player: "Jon Rahm",
            composite: 84.5,
            course_fit: 81.2,
            form: 83.7,
            momentum: 79.1,
            momentum_direction: "hot",
            course_confidence: 0.82,
            course_rounds: 26,
            weather_adjustment: 0.6,
            availability: { status: "fit" },
            form_flags: ["recent_withdrawal_risk"],
            form_notes: ["Back in field this week."],
            details: {
              course_components: { driving: 1.2 },
              form_components: { consistency: 0.9 },
              momentum_windows: { w12: 0.4 },
            },
          },
        ],
        matchup_bets: [],
        value_bets: {},
      },
    }

    const run = buildHydratedPredictionRun(snapshot, "live")
    expect(run).not.toBeNull()
    expect(run?.composite_results).toHaveLength(1)
    const player = run?.composite_results?.[0]
    expect(player?.availability).toEqual({ status: "fit" })
    expect(player?.form_flags).toEqual(["recent_withdrawal_risk"])
    expect(player?.form_notes).toEqual(["Back in field this week."])
    expect(player?.details?.course_components?.driving).toBe(1.2)
  })

  it("returns empty rankings and warning when eligibility fails", () => {
    const snapshot: LiveRefreshSnapshot = {
      live_tournament: {
        event_name: "Masters Tournament",
        course_name: "Augusta National",
        eligibility: {
          verified: false,
          summary: "Field verification failed.",
          action: "Retry after field updates.",
        },
      },
    }

    const run = buildHydratedPredictionRun(snapshot, "live")
    expect(run).not.toBeNull()
    expect(run?.composite_results).toEqual([])
    expect(run?.warnings?.[0]).toContain("Field verification failed.")
  })

  it("hydrates a direct snapshot section for past-event replay", () => {
    const run = buildPredictionRunFromSection({
      event_name: "Zurich Classic",
      course_name: "TPC Louisiana",
      field_size: 80,
      rankings: [
        {
          rank: 1,
          player_key: "collin_morikawa",
          player: "Collin Morikawa",
          composite: 75.2,
          course_fit: 70.1,
          form: 72.0,
          momentum: 68.2,
        },
      ],
      matchup_bets_all_books: [
        {
          pick: "Collin Morikawa",
          pick_key: "collin_morikawa",
          opponent: "Xander Schauffele",
          opponent_key: "xander_schauffele",
          book: "bet365",
          odds: "+105",
          model_win_prob: 0.54,
          implied_prob: 0.49,
          ev: 0.08,
          ev_pct: "8.0%",
          composite_gap: 2.1,
          form_gap: 1.4,
          course_fit_gap: 0.8,
          reason: "Stored from runtime snapshot",
        },
      ],
      value_bets: {},
    })

    expect(run).not.toBeNull()
    expect(run?.event_name).toBe("Zurich Classic")
    expect(run?.matchup_bets_all_books?.length).toBe(1)
  })

  it("uses best_odds fallback for secondary market rows", () => {
    const run = buildPredictionRunFromSection({
      event_name: "Zurich Classic",
      value_bets: {
        outright: [
          {
            player: "J.J. Spaun",
            player_display: "J.J. Spaun",
            player_key: "jj_spaun",
            bet_type: "outright",
            odds: "",
            best_book: "draftkings",
            best_odds: 13000,
            ev: 0.25,
            is_value: true,
          },
        ],
      },
    })

    const flattened = flattenSecondaryBets(run)
    expect(flattened).toHaveLength(1)
    expect(flattened[0].odds).toBe("+13000")
  })
})
