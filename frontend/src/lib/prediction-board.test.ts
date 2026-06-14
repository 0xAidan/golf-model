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

  it("passes model_variant and ranking_source from the snapshot section", () => {
    const run = buildPredictionRunFromSection({
      event_name: "Test Open",
      model_variant: "baseline",
      ranking_source: "lab_current_event_model",
      rankings: [
        {
          rank: 1,
          player_key: "scottie_scheffler",
          player: "Scottie Scheffler",
          composite: 90,
          course_fit: 88,
          form: 87,
          momentum: 85,
        },
      ],
      matchup_bets: [],
      value_bets: {},
    })
    expect(run?.model_variant).toBe("baseline")
    expect(run?.ranking_source).toBe("lab_current_event_model")
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
    expect(flattened[0].player_key).toBe("jj_spaun")
  })

  it("hydrates live-player-board momentum fields when preferLivePlayerBoard is true", () => {
    const run = buildPredictionRunFromSection(
      {
        event_name: "Live Event",
        live_player_board: [
          {
            player_key: "tommy_fleetwood",
            player: "Tommy Fleetwood",
            model: {
              start_rank: 12,
              current_rank: 4,
              rank_delta: 8,
              composite: 79.2,
              start_composite: 73.8,
              momentum: 76,
              momentum_trend: 0.4,
              momentum_direction: "hot",
            },
            scoring: {
              position_label: "T3",
              position_rank: 3,
              start_position: "T15",
              start_position_rank: 15,
              position_delta: 12,
              total_to_par: -8,
              baseline_source: "frozen_at_tee_off",
            },
          },
        ],
        rankings: [],
        value_bets: {},
      },
      { preferLivePlayerBoard: true, hydrationSection: "live" },
    )

    expect(run?.composite_results?.[0]?.momentum_trend).toBe(0.4)
    expect(run?.composite_results?.[0]?.momentum_direction).toBe("hot")
  })

  it("hydrates live-player-board when preferLivePlayerBoard is true", () => {
    const run = buildPredictionRunFromSection(
      {
        event_name: "Live Event",
        live_player_board: [
          {
            player_key: "tommy_fleetwood",
            player: "Tommy Fleetwood",
            model: {
              start_rank: 12,
              current_rank: 4,
              rank_delta: 8,
              composite: 79.2,
              start_composite: 73.8,
            },
            scoring: {
              position_label: "T3",
              position_rank: 3,
              start_position: "T15",
              start_position_rank: 15,
              position_delta: 12,
              total_to_par: -8,
              baseline_source: "frozen_at_tee_off",
            },
          },
        ],
        rankings: [
          {
            rank: 99,
            player_key: "tommy_fleetwood",
            player: "Tommy Fleetwood",
            composite: 50,
            course_fit: 50,
            form: 50,
            momentum: 50,
          },
        ],
        value_bets: {},
      },
      { preferLivePlayerBoard: true, hydrationSection: "live" },
    )

    expect(run?.composite_results?.[0]?.start_rank).toBe(12)
    expect(run?.composite_results?.[0]?.rank_delta).toBe(8)
    expect(run?.composite_results?.[0]?.leaderboard_position).toBe("T3")
    expect(run?.hydration_section).toBe("live")
  })

  it("upcoming hydration uses rankings not live_player_board", () => {
    const run = buildPredictionRunFromSection(
      {
        event_name: "Upcoming Event",
        live_player_board: [
          {
            player_key: "player_a",
            player: "Player A",
            model: { current_rank: 1, composite: 90 },
            scoring: { position_label: "T1", total_to_par: -5 },
          },
        ],
        rankings: [
          {
            rank: 3,
            player_key: "player_a",
            player: "Player A",
            composite: 78,
            course_fit: 72,
            form: 74,
            momentum: 70,
          },
        ],
        value_bets: {},
      },
      { preferLivePlayerBoard: false, hydrationSection: "upcoming" },
    )

    expect(run?.composite_results?.[0]?.rank).toBe(3)
    expect(run?.composite_results?.[0]?.form).toBe(74)
    expect(run?.composite_results?.[0]?.leaderboard_position).toBeUndefined()
    expect(run?.hydration_section).toBe("upcoming")
  })

  it("records fallback section when upcoming uses live snapshot", () => {
    const snapshot: LiveRefreshSnapshot = {
      live_tournament: {
        event_name: "Live Only",
        rankings: [
          {
            rank: 1,
            player_key: "a",
            player: "A",
            composite: 80,
            course_fit: 70,
            form: 70,
            momentum: 70,
          },
        ],
        matchup_bets: [],
        value_bets: {},
      },
    }

    const run = buildHydratedPredictionRun(snapshot, "upcoming")
    expect(run?.hydration_section).toBe("upcoming_fallback_live")
    expect(run?.warnings?.some((w) => w.includes("Upcoming board is using live"))).toBe(true)
  })

  it("preserves new-live flags on matchup and secondary rows", () => {
    const run = buildPredictionRunFromSection({
      event_name: "Live Event",
      rankings: [],
      matchup_bets: [
        {
          pick: "Player A",
          pick_key: "player_a",
          opponent: "Player B",
          opponent_key: "player_b",
          odds: "+110",
          book: "fanduel",
          model_win_prob: 0.56,
          implied_prob: 0.5,
          ev: 0.1,
          ev_pct: "10.0%",
          composite_gap: 2,
          form_gap: 1,
          course_fit_gap: 1,
          reason: "Edge",
          is_new_live_opportunity: true,
          first_seen_at: "2026-06-04T16:00:00Z",
        },
      ],
      value_bets: {
        top10: [
          {
            player: "Player A",
            player_key: "player_a",
            bet_type: "top10",
            odds: "+400",
            book: "fanduel",
            ev: 0.2,
            is_value: true,
            is_new_live_opportunity: true,
            first_seen_at: "2026-06-04T16:00:00Z",
          },
        ],
      },
    })

    expect(run?.matchup_bets?.[0]?.is_new_live_opportunity).toBe(true)
    const flattened = flattenSecondaryBets(run)
    expect(flattened[0]?.is_new_live_opportunity).toBe(true)
    expect(flattened[0]?.first_seen_at).toBe("2026-06-04T16:00:00Z")
  })

  it("live board hydrates momentum_trend from live_player_board", () => {
    const run = buildPredictionRunFromSection(
      {
        event_name: "Live Event",
        live_player_board: [
          {
            player_key: "player_a",
            player: "Player A",
            model: {
              current_rank: 1,
              composite: 80,
              momentum_trend: 0.55,
              momentum_direction: "hot",
            },
            scoring: { position_label: "T1", total_to_par: -5 },
          },
        ],
        rankings: [],
        value_bets: {},
      },
      { preferLivePlayerBoard: true, hydrationSection: "live" },
    )
    expect(run?.composite_results?.[0]?.momentum_trend).toBe(0.55)
    expect(run?.composite_results?.[0]?.momentum_direction).toBe("hot")
  })
})
