import { describe, expect, it } from "vitest"

import {
  buildCourseFeedModel,
  buildDiagnosticsModel,
  buildLeaderboardModel,
  buildMarketIntelModel,
  buildReplayTimelineModel,
} from "@/lib/cockpit-event-models"
import type {
  CompositePlayer,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  PastMarketPredictionRow,
  PastTimelinePoint,
} from "@/lib/types"

const basePlayers: CompositePlayer[] = [
  {
    player_key: "scottie_scheffler",
    player_display: "Scottie Scheffler",
    rank: 1,
    composite: 92.4,
    course_fit: 90.1,
    form: 93.8,
    momentum: 88.5,
    weather_adjustment: 0.6,
  },
  {
    player_key: "collin_morikawa",
    player_display: "Collin Morikawa",
    rank: 2,
    composite: 89.1,
    course_fit: 88.2,
    form: 87.6,
    momentum: 84.4,
    weather_adjustment: -0.3,
  },
]

const replayPoints: PastTimelinePoint[] = [
  {
    snapshot_id: "snap-2",
    generated_at: "2026-04-13T18:00:00Z",
    section: "live",
    active: true,
    diagnostics_state: "edges_available",
    leaderboard_count: 12,
    rankings_count: 10,
    matchup_count: 22,
    value_pick_count: 4,
    best_edge: 0.094,
  },
  {
    snapshot_id: "snap-1",
    generated_at: "2026-04-13T14:00:00Z",
    section: "live",
    active: true,
    diagnostics_state: "no_market_posted_yet",
    leaderboard_count: 8,
    rankings_count: 10,
    matchup_count: 0,
    value_pick_count: 0,
    best_edge: null,
  },
]

describe("buildLeaderboardModel", () => {
  it("seeds the leaderboard from rankings in upcoming mode when no scores exist yet", () => {
    const model = buildLeaderboardModel({
      mode: "upcoming",
      leaderboardRows: [],
      players: basePlayers,
    })

    expect(model.seededFromRankings).toBe(true)
    expect(model.rows[0]).toMatchObject({
      positionLabel: "Model 1",
      playerLabel: "Scottie Scheffler",
      toParLabel: "Pre",
    })
    expect(model.emptyMessage).toBeNull()
  })
})

describe("buildMarketIntelModel", () => {
  it("prefers persisted past-market history in past mode", () => {
    const pastRows: PastMarketPredictionRow[] = [
      {
        snapshot_id: "snap-2",
        event_id: "evt-1",
        section: "live",
        market_family: "matchup",
        player_key: "scottie_scheffler",
        player_display: "Scottie Scheffler",
        opponent_key: "rory_mcilroy",
        opponent_display: "Rory McIlroy",
        book: "bet365",
        odds: "-110",
        ev: 0.12,
        generated_at: "2026-04-13T18:00:00Z",
      },
      {
        snapshot_id: "snap-1",
        event_id: "evt-1",
        section: "live",
        market_family: "placement",
        market_type: "top10",
        player_key: "collin_morikawa",
        player_display: "Collin Morikawa",
        book: "draftkings",
        odds: "+250",
        ev: 0.08,
        generated_at: "2026-04-13T16:00:00Z",
      },
    ]

    const model = buildMarketIntelModel({
      mode: "past",
      currentSecondaryBets: [],
      pastMarketRows: pastRows,
    })

    expect(model.metrics[0]).toMatchObject({ label: "History rows", value: "2" })
    expect(model.rows[0]).toMatchObject({
      label: "Scottie Scheffler over Rory McIlroy",
      eyebrow: "Historical matchup",
      edgeLabel: "12.0%",
    })
  })
})

describe("buildReplayTimelineModel", () => {
  it("turns stored replay captures into a real past-mode timeline", () => {
    const model = buildReplayTimelineModel({
      mode: "past",
      timelinePoints: replayPoints,
      currentGeneratedAt: null,
      snapshotAgeSeconds: null,
    })

    expect(model.metrics[0]).toMatchObject({ label: "Replay captures", value: "2" })
    expect(model.metrics[1]).toMatchObject({ label: "Best captured edge", value: "9.4%" })
    expect(model.items[0]?.detail).toContain("22 matchup rows")
    expect(model.emptyMessage).toBeNull()
  })
})

describe("buildCourseFeedModel", () => {
  it("uses replay history to make the left-rail feed time-aware in past mode", () => {
    const model = buildCourseFeedModel({
      mode: "past",
      snapshotAgeSeconds: null,
      snapshotNotice: null,
      players: basePlayers,
      timelinePoints: replayPoints,
      diagnosticsState: "edges_available",
      fieldValidation: {
        major_event: false,
        cross_tour_backfill_used: false,
        players_checked: 0,
        players_with_thin_rounds: ["Player A"],
        players_missing_dg_skill: [],
        has_cross_tour_field_risk: true,
      },
    })

    expect(model.metrics[0]).toMatchObject({ label: "Replay captures", value: "2" })
    expect(model.feedItems[0]?.label).toBe("Replay timeline")
    expect(model.feedItems[0]?.detail).toContain("snapshots captured")
  })
})

describe("buildDiagnosticsModel", () => {
  it("sorts reason codes and attaches selected-event grading context", () => {
    const gradingHistory: GradedTournamentSummary[] = [
      {
        event_id: "evt-1",
        name: "RBC Heritage",
        graded_pick_count: 5,
        hits: 3,
        total_profit: 1.2,
      },
    ]
    const currentSecondaryBets: FlattenedSecondaryBet[] = [
      {
        player: "Collin Morikawa",
        market: "Top 10",
        odds: "+250",
        book: "draftkings",
        ev: 0.08,
      },
    ]

    const model = buildDiagnosticsModel({
      mode: "past",
      diagnostics: {
        state: "edges_available",
        reason_codes: {
          missing_display_odds: 4,
          missing_composite_player: 2,
        },
        market_counts: {
          tournament_matchups: {
            raw_rows: 12,
          },
        },
        selection_counts: {
          selected_rows: 3,
          all_qualifying_rows: 7,
        },
        value_filters: {
          missing_display_odds: 4,
        },
      },
      dashboardAiAvailable: true,
      strategySource: "registry",
      strategyName: "weekly-live",
      warnings: ["Stored replay warning."],
      gradingHistory,
      selectedEventId: "evt-1",
      timelinePoints: replayPoints,
      currentSecondaryBets,
    })

    expect(model.reasonCodes[0]).toMatchObject({ label: "missing display odds", count: 4 })
    expect(model.metrics).toContainEqual(
      expect.objectContaining({ label: "Replay captures", value: "2" }),
    )
    expect(model.selectedEventSummary).toMatchObject({
      name: "RBC Heritage",
      profitLabel: "+1.20u",
    })
  })
})
