import test from "node:test"
import assert from "node:assert/strict"

import { buildHydratedPredictionRun, collectAvailableBooks, flattenSecondaryBets } from "../src/lib/prediction-board.ts"
import type { LiveRefreshSnapshot } from "../src/lib/types"

test("buildHydratedPredictionRun preserves full snapshot board payloads", () => {
  const snapshot: LiveRefreshSnapshot = {
    live_tournament: {
      event_name: "Masters",
      course_name: "Augusta National",
      field_size: 92,
      tournament_id: 10,
      course_num: 4,
      rankings: [
        {
          rank: 1,
          player_key: "scottie_scheffler",
          player: "Scottie Scheffler",
          composite: 91,
          form: 89,
          course_fit: 88,
          momentum: 84,
        },
      ],
      matchups: [
        {
          player: "Legacy Row",
          opponent: "Legacy Opp",
          bookmaker: "fanduel",
          market_odds: "+100",
          model_prob: 0.51,
          ev: 0.01,
        },
      ],
      matchup_bets: [
        {
          pick: "Scottie Scheffler",
          pick_key: "scottie_scheffler",
          opponent: "Rory McIlroy",
          opponent_key: "rory_mcilroy",
          odds: "+118",
          book: "betonline",
          model_win_prob: 0.58,
          implied_prob: 0.46,
          ev: 0.11,
          ev_pct: "11.0%",
          composite_gap: 3.1,
          form_gap: 2.4,
          course_fit_gap: 2.2,
          reason: "Best number posted",
        },
        {
          pick: "Scottie Scheffler",
          pick_key: "scottie_scheffler",
          opponent: "Rory McIlroy",
          opponent_key: "rory_mcilroy",
          odds: "+112",
          book: "bet365",
          model_win_prob: 0.58,
          implied_prob: 0.47,
          ev: 0.09,
          ev_pct: "9.0%",
          composite_gap: 3.1,
          form_gap: 2.4,
          course_fit_gap: 2.2,
          reason: "Still qualifies",
        },
      ],
      matchup_bets_all_books: [
        {
          pick: "Scottie Scheffler",
          pick_key: "scottie_scheffler",
          opponent: "Rory McIlroy",
          opponent_key: "rory_mcilroy",
          odds: "+118",
          book: "betonline",
          model_win_prob: 0.58,
          implied_prob: 0.46,
          ev: 0.11,
          ev_pct: "11.0%",
          composite_gap: 3.1,
          form_gap: 2.4,
          course_fit_gap: 2.2,
          reason: "Best number posted",
        },
        {
          pick: "Scottie Scheffler",
          pick_key: "scottie_scheffler",
          opponent: "Rory McIlroy",
          opponent_key: "rory_mcilroy",
          odds: "+112",
          book: "bet365",
          model_win_prob: 0.58,
          implied_prob: 0.47,
          ev: 0.09,
          ev_pct: "9.0%",
          composite_gap: 3.1,
          form_gap: 2.4,
          course_fit_gap: 2.2,
          reason: "Still qualifies",
        },
        {
          pick: "Scottie Scheffler",
          pick_key: "scottie_scheffler",
          opponent: "Rory McIlroy",
          opponent_key: "rory_mcilroy",
          odds: "+108",
          book: "draftkings",
          model_win_prob: 0.58,
          implied_prob: 0.48,
          ev: 0.08,
          ev_pct: "8.0%",
          composite_gap: 3.1,
          form_gap: 2.4,
          course_fit_gap: 2.2,
          reason: "Additional qualifying line",
        },
      ],
      value_bets: {
        top10: [
          {
            player_display: "Scottie Scheffler",
            player_key: "scottie_scheffler",
            bet_type: "top10",
            odds: "+175",
            book: "bovada",
            ev: 0.14,
            ev_pct: "14.0%",
            is_value: true,
          },
          {
            player_display: "Scottie Scheffler",
            player_key: "scottie_scheffler",
            bet_type: "top10",
            odds: "+170",
            book: "bet365",
            ev: 0.12,
            ev_pct: "12.0%",
            is_value: true,
          },
          {
            player_display: "Scottie Scheffler",
            player_key: "scottie_scheffler",
            bet_type: "top10",
            odds: "+180",
            book: "datagolf",
            ev: 0.16,
            ev_pct: "16.0%",
            is_value: true,
          },
        ],
      },
    },
  }

  const hydrated = buildHydratedPredictionRun(snapshot, "live")

  assert.ok(hydrated)
  assert.deepEqual(
    hydrated.matchup_bets?.map((row) => row.book),
    ["betonline", "bet365"],
  )
  assert.deepEqual(
    hydrated.matchup_bets_all_books?.map((row) => row.book),
    ["betonline", "bet365", "draftkings"],
  )
  assert.deepEqual(
    hydrated.value_bets?.top10?.map((row) => row.book),
    ["bovada", "bet365"],
  )
  assert.deepEqual(collectAvailableBooks(hydrated), ["bet365", "betonline", "bovada", "draftkings"])
  assert.deepEqual(
    flattenSecondaryBets(hydrated).map((row) => row.book),
    ["bovada", "bet365"],
  )
})

test("buildHydratedPredictionRun respects explicit empty matchup payloads", () => {
  const snapshot: LiveRefreshSnapshot = {
    live_tournament: {
      event_name: "Masters",
      matchups: [
        {
          player: "Legacy Row",
          opponent: "Legacy Opp",
          bookmaker: "bet365",
          market_odds: "+100",
          model_prob: 0.55,
          ev: 0.03,
        },
      ],
      matchup_bets: [],
    },
  }

  const hydrated = buildHydratedPredictionRun(snapshot, "live")

  assert.ok(hydrated)
  assert.deepEqual(hydrated.matchup_bets, [])
})

test("buildHydratedPredictionRun tolerates null snapshot board payloads", () => {
  const snapshot = {
    live_tournament: {
      event_name: "Masters",
      matchup_bets: null,
      value_bets: null,
    },
  } as unknown as LiveRefreshSnapshot

  const hydrated = buildHydratedPredictionRun(snapshot, "live")

  assert.ok(hydrated)
  assert.deepEqual(hydrated.matchup_bets, [])
  assert.deepEqual(hydrated.value_bets, {})
})
