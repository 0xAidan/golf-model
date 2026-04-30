import { formatDateTime, formatNumber, formatPercent, formatUnits } from "@/lib/format"
import type {
  CompositePlayer,
  FieldValidation,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveLeaderboardRow,
  PastMarketPredictionRow,
  PastTimelinePoint,
} from "@/lib/types"

export type CockpitMode = "live" | "upcoming" | "test" | "past"

export type CockpitMetricModel = {
  label: string
  value: string
  detail?: string
  tone?: "default" | "positive" | "warning"
}

export type CockpitFeedItemModel = {
  label: string
  detail: string
}

export type CockpitLeaderboardRowModel = {
  positionLabel: string
  playerLabel: string
  playerKey?: string | null
  toParLabel: string
  roundLabel: string
  scoreLabel: string
  detail?: string
}

export type CockpitMarketIntelRowModel = {
  eyebrow: string
  label: string
  playerKey?: string | null
  opponentKey?: string | null
  edgeLabel: string
  priceLabel: string
  detail: string
}

export type CockpitReplayItemModel = {
  label: string
  detail: string
}

export type CockpitReasonCodeModel = {
  label: string
  count: number
}

export type CockpitSelectedEventSummary = {
  name: string
  hitsLabel: string
  profitLabel: string
}

type DiagnosticsInput = {
  state?: string
  reason_codes?: Record<string, number>
  market_counts?: Record<string, { raw_rows?: number; reason_code?: string }>
  selection_counts?: {
    selected_rows?: number
    all_qualifying_rows?: number
  }
  value_filters?: {
    missing_display_odds?: number
    ev_cap_filtered?: number
    probability_inconsistency_filtered?: number
  }
}

export function buildCourseFeedModel({
  mode,
  snapshotAgeSeconds,
  snapshotNotice,
  players,
  timelinePoints,
  diagnosticsState,
  fieldValidation,
}: {
  mode: CockpitMode
  snapshotAgeSeconds: number | null
  snapshotNotice: string | null
  players: CompositePlayer[]
  timelinePoints: PastTimelinePoint[]
  diagnosticsState?: string
  fieldValidation?: FieldValidation
}) {
  const strongestWeatherAdjustment = players.reduce<number | null>((current, player) => {
    const value = player.weather_adjustment
    if (value === null || value === undefined || Number.isNaN(value)) {
      return current
    }
    if (current === null || Math.abs(value) > Math.abs(current)) {
      return value
    }
    return current
  }, null)
  const adjustedPlayers = players.filter((player) => Math.abs(player.weather_adjustment ?? 0) >= 0.15).length

  const metrics: CockpitMetricModel[] =
    mode === "past"
      ? [
          {
            label: "Replay captures",
            value: String(timelinePoints.length),
            detail:
              timelinePoints.length > 0
                ? `Latest ${formatDateTime(timelinePoints[0]?.generated_at)}`
                : "No stored replay captures",
          },
          {
            label: "Weather lean",
            value: formatSignedNumber(strongestWeatherAdjustment),
            detail:
              adjustedPlayers > 0
                ? `${adjustedPlayers} ranked players carried non-zero weather adjustments`
                : "No material weather adjustment in the visible board",
          },
          {
            label: "Field risk",
            value: fieldValidation?.has_cross_tour_field_risk ? "Review" : "Healthy",
            detail: buildFieldRiskDetail(fieldValidation),
            tone: fieldValidation?.has_cross_tour_field_risk ? "warning" : "default",
          },
        ]
      : [
          {
            label: "Snapshot freshness",
            value: snapshotAgeSeconds === null ? "Waiting" : `${snapshotAgeSeconds}s`,
            detail:
              snapshotAgeSeconds === null
                ? "No current snapshot has landed yet"
                : "Time since the cockpit last refreshed this event surface",
          },
          {
            label: "Weather lean",
            value: formatSignedNumber(strongestWeatherAdjustment),
            detail:
              adjustedPlayers > 0
                ? `${adjustedPlayers} ranked players carry weather adjustments`
                : "No material weather adjustment in the visible board",
          },
          {
            label: "Field risk",
            value: fieldValidation?.has_cross_tour_field_risk ? "Review" : "Healthy",
            detail: buildFieldRiskDetail(fieldValidation),
            tone: fieldValidation?.has_cross_tour_field_risk ? "warning" : "default",
          },
        ]

  const feedItems: CockpitFeedItemModel[] = []

  if (mode === "past") {
    if (timelinePoints.length > 0) {
      const oldestPoint = timelinePoints[timelinePoints.length - 1]
      feedItems.push({
        label: "Replay timeline",
        detail: `${timelinePoints.length} snapshots captured from ${formatDateTime(timelinePoints[0]?.generated_at)} back to ${formatDateTime(oldestPoint?.generated_at)}.`,
      })
    } else {
      feedItems.push({
        label: "Replay timeline",
        detail: "No immutable snapshot history has been captured for this event yet.",
      })
    }
  } else {
    feedItems.push({
      label: mode === "live" ? "Active feed" : "Pre-event feed",
      detail:
        mode === "live"
          ? "This rail tracks the current event state, field warnings, and surface freshness."
          : "This rail stays focused on pre-tournament context until live scoring begins.",
    })
  }

  if (snapshotNotice) {
    feedItems.push({
      label: "Snapshot note",
      detail: snapshotNotice,
    })
  }

  if (diagnosticsState) {
    feedItems.push({
      label: mode === "past" ? "Replay state" : "Market state",
      detail: diagnosticsState.replaceAll("_", " "),
    })
  }

  if ((fieldValidation?.players_with_thin_rounds?.length ?? 0) > 0) {
    feedItems.push({
      label: "Thin-round caution",
      detail: `${fieldValidation?.players_with_thin_rounds?.length ?? 0} players were flagged with shallow sample depth.`,
    })
  }

  return {
    metrics,
    feedItems,
  }
}

export function buildLeaderboardModel({
  mode,
  leaderboardRows,
  players,
}: {
  mode: CockpitMode
  leaderboardRows: LiveLeaderboardRow[]
  players: CompositePlayer[]
}) {
  if (leaderboardRows.length > 0) {
    const rows = leaderboardRows.slice(0, 10).map((row) => ({
      positionLabel: row.position ?? String(row.rank ?? "--"),
      playerLabel: row.player,
      playerKey: row.player_key,
      toParLabel: formatToParValue(row.total_to_par),
      roundLabel: row.latest_round_num ? `R${row.latest_round_num}` : "--",
      scoreLabel: row.latest_round_score === null || row.latest_round_score === undefined ? "--" : String(row.latest_round_score),
      detail: row.finish_state ?? undefined,
    }))

    return {
      metrics: [
        {
          label: "Leader",
          value: rows[0]?.playerLabel ?? "--",
          detail: rows[0]?.positionLabel ? `Position ${rows[0].positionLabel}` : undefined,
        },
        {
          label: "Visible rows",
          value: String(rows.length),
          detail: "Top of the stored leaderboard",
        },
        {
          label: "Rounds logged",
          value: String(
            Math.max(
              0,
              ...leaderboardRows.map((row) =>
                row.latest_round_num === null || row.latest_round_num === undefined ? 0 : row.latest_round_num,
              ),
            ),
          ),
          detail: "Highest round number visible in the board",
        },
      ],
      rows,
      seededFromRankings: false,
      emptyMessage: null,
    }
  }

  if ((mode === "upcoming" || mode === "test") && players.length > 0) {
    const rows = players.slice(0, 8).map((player) => ({
      positionLabel: `Model ${player.rank}`,
      playerLabel: player.player_display,
      playerKey: player.player_key,
      toParLabel: "Pre",
      roundLabel: "--",
      scoreLabel: formatNumber(player.composite, 1),
      detail: `${formatNumber(player.course_fit, 1)} course · ${formatNumber(player.form, 1)} form`,
    }))

    return {
      metrics: [
        {
          label: "Opening watchlist",
          value: rows[0]?.playerLabel ?? "--",
          detail: "Model favorite before scoring begins",
        },
        {
          label: "Seeded rows",
          value: String(rows.length),
          detail: "Pre-tournament board seeded from rankings",
        },
        {
          label: "Top composite",
          value: rows[0]?.scoreLabel ?? "--",
          detail: "Best available pre-event model score",
        },
      ],
      rows,
      seededFromRankings: true,
      emptyMessage: null,
    }
  }

  return {
    metrics: [] as CockpitMetricModel[],
    rows: [] as CockpitLeaderboardRowModel[],
    seededFromRankings: false,
    emptyMessage:
      mode === "past"
        ? "Replay snapshot did not preserve leaderboard rows for this event."
        : mode === "live"
          ? "No live leaderboard rows are available for the current event yet."
          : "No pre-tournament leaderboard seed is available yet.",
  }
}

export function buildMarketIntelModel({
  mode,
  currentSecondaryBets,
  pastMarketRows,
}: {
  mode: CockpitMode
  currentSecondaryBets: FlattenedSecondaryBet[]
  pastMarketRows: PastMarketPredictionRow[]
}) {
  if (mode === "past" && pastMarketRows.length > 0) {
    const sortedRows = [...pastMarketRows].sort((left, right) => {
      const edgeDiff = Number(right.ev ?? 0) - Number(left.ev ?? 0)
      if (edgeDiff !== 0) {
        return edgeDiff
      }
      return String(right.generated_at ?? "").localeCompare(String(left.generated_at ?? ""))
    })

    return {
      metrics: [
        {
          label: "History rows",
          value: String(sortedRows.length),
          detail: "Stored pricing rows captured during the event",
        },
        {
          label: "Books seen",
          value: String(countDistinct(sortedRows.map((row) => row.book))),
          detail: "Unique books represented in replay history",
        },
        {
          label: "Best edge",
          value: formatPercent(sortedRows[0]?.ev ?? null),
          detail: "Highest captured historical edge",
        },
      ],
      rows: sortedRows.slice(0, 8).map((row) => ({
        eyebrow: row.market_family === "matchup" ? "Historical matchup" : `Historical ${row.market_type ?? row.market_family}`,
        label: buildPastMarketLabel(row),
        playerKey: row.player_key,
        opponentKey: row.opponent_key,
        edgeLabel: formatPercent(row.ev ?? null),
        priceLabel: row.odds ?? "--",
        detail: [row.book, formatDateTime(row.generated_at)].filter(Boolean).join(" · "),
      })),
      emptyMessage: null,
    }
  }

  if (currentSecondaryBets.length > 0) {
    const sortedBets = [...currentSecondaryBets].sort((left, right) => right.ev - left.ev)
    return {
      metrics: [
        {
          label: mode === "past" ? "Latest rows" : "Current rows",
          value: String(sortedBets.length),
          detail:
            mode === "live"
              ? "Current secondary markets visible in the active cockpit"
              : mode === "test"
                ? "Secondary markets available in the experimental v5 lane"
                : "Secondary markets available for the selected event context",
        },
        {
          label: "Books seen",
          value: String(countDistinct(sortedBets.map((bet) => bet.book))),
          detail: "Unique books represented in the current rows",
        },
        {
          label: "Best edge",
          value: formatPercent(sortedBets[0]?.ev ?? null),
          detail: "Highest current secondary-market edge",
        },
      ],
      rows: sortedBets.slice(0, 8).map((bet) => ({
        eyebrow:
          mode === "live"
            ? "Live market"
            : mode === "upcoming" || mode === "test"
              ? "Pre-tournament market"
              : "Latest snapshot",
        label: bet.player,
        playerKey: bet.player_key,
        edgeLabel: formatPercent(bet.ev),
        priceLabel: bet.odds,
        detail: [bet.market, bet.book].filter(Boolean).join(" · "),
      })),
      emptyMessage: null,
    }
  }

  return {
    metrics: [] as CockpitMetricModel[],
    rows: [] as CockpitMarketIntelRowModel[],
    emptyMessage:
      mode === "past"
        ? "No historical market intel rows were captured for this replay yet."
        : mode === "live"
          ? "No secondary market edges are currently active in the live cockpit."
          : "No pre-tournament secondary market edges are available yet.",
  }
}

export function buildReplayTimelineModel({
  mode,
  timelinePoints,
  currentGeneratedAt,
  snapshotAgeSeconds,
}: {
  mode: CockpitMode
  timelinePoints: PastTimelinePoint[]
  currentGeneratedAt: string | null
  snapshotAgeSeconds: number | null
}) {
  if (mode === "past" && timelinePoints.length > 0) {
    const bestCapturedEdge = timelinePoints.reduce<number | null>((current, point) => {
      if (point.best_edge === null || point.best_edge === undefined || Number.isNaN(point.best_edge)) {
        return current
      }
      if (current === null || point.best_edge > current) {
        return point.best_edge
      }
      return current
    }, null)

    return {
      metrics: [
        {
          label: "Replay captures",
          value: String(timelinePoints.length),
          detail: "Ordered immutable snapshots for this event",
        },
        {
          label: "Best captured edge",
          value: formatPercent(bestCapturedEdge),
          detail: "Highest edge surfaced anywhere in the replay",
        },
        {
          label: "Latest capture",
          value: formatDateTime(timelinePoints[0]?.generated_at),
          detail: "Most recent stored replay point",
        },
      ],
      items: timelinePoints.slice(0, 8).map((point) => ({
        label: formatDateTime(point.generated_at),
        detail: [
          `${point.matchup_count} matchup rows`,
          `${point.value_pick_count} secondary rows`,
          `${point.leaderboard_count} leaderboard rows`,
          point.best_edge !== null && point.best_edge !== undefined ? `best edge ${formatPercent(point.best_edge)}` : null,
        ]
          .filter(Boolean)
          .join(" · "),
      })),
      emptyMessage: null,
    }
  }

  if (mode === "past") {
    return {
      metrics: [] as CockpitMetricModel[],
      items: [] as CockpitReplayItemModel[],
      emptyMessage: "No replay timeline has been stored for this completed event yet.",
    }
  }

  return {
    metrics: [
      {
        label: "Current capture",
        value: currentGeneratedAt ? formatDateTime(currentGeneratedAt) : "Waiting",
        detail:
          snapshotAgeSeconds === null
            ? "Replay history starts once snapshots are captured"
            : `Current snapshot is ${snapshotAgeSeconds}s old`,
      },
    ],
    items: [] as CockpitReplayItemModel[],
    emptyMessage:
      mode === "live"
        ? "Replay history becomes reviewable in Past mode after snapshots accumulate for this event."
        : "Past-mode replay unlocks once the event has real snapshot history to review.",
  }
}

export function buildDiagnosticsModel({
  mode,
  diagnostics,
  dashboardAiAvailable,
  strategySource,
  strategyName,
  warnings,
  gradingHistory,
  selectedEventId,
  timelinePoints,
  currentSecondaryBets,
}: {
  mode: CockpitMode
  diagnostics?: DiagnosticsInput
  dashboardAiAvailable: boolean
  strategySource?: string
  strategyName?: string
  warnings?: string[]
  gradingHistory: GradedTournamentSummary[]
  selectedEventId?: string
  timelinePoints: PastTimelinePoint[]
  currentSecondaryBets: FlattenedSecondaryBet[]
}) {
  const rawRows = diagnostics?.market_counts?.tournament_matchups?.raw_rows ?? 0
  const selectedRows = diagnostics?.selection_counts?.selected_rows ?? 0
  const qualifyingRows = diagnostics?.selection_counts?.all_qualifying_rows ?? 0
  const selectedEvent = gradingHistory.find((event) => event.event_id === selectedEventId)

  return {
    metrics: [
      {
        label: "Snapshot state",
        value: diagnostics?.state ?? "unknown",
        detail: "Latest pipeline state for this cockpit surface",
      },
      {
        label: "AI layer",
        value: dashboardAiAvailable ? "Enabled" : "Unavailable",
        detail: dashboardAiAvailable ? "Qualitative context is available" : "AI context is currently unavailable",
        tone: dashboardAiAvailable ? "positive" : "warning",
      },
      {
        label: "Strategy source",
        value: strategyName ?? strategySource ?? "--",
        detail: strategySource ? `Source: ${strategySource}` : "No explicit runtime strategy metadata",
      },
      {
        label: mode === "past" ? "Replay captures" : "Rows selected",
        value: mode === "past" ? String(timelinePoints.length) : String(selectedRows),
        detail:
          mode === "past"
            ? "Stored replay points available for grading review"
            : `${qualifyingRows} qualifying rows from ${rawRows} raw matchup rows`,
      },
    ] as CockpitMetricModel[],
    counters: [
      `Matchup rows posted: ${String(rawRows)}`,
      `Rows qualifying: ${String(qualifyingRows)}`,
      `Rows selected: ${String(selectedRows)}`,
      `Current secondary rows: ${String(currentSecondaryBets.length)}`,
      `Rows filtered (missing odds): ${String(diagnostics?.value_filters?.missing_display_odds ?? 0)}`,
    ],
    reasonCodes: Object.entries(diagnostics?.reason_codes ?? {})
      .sort((left, right) => right[1] - left[1])
      .slice(0, 6)
      .map(([label, count]) => ({
        label: label.replaceAll("_", " "),
        count,
      })),
    warnings: warnings ?? [],
    selectedEventSummary: selectedEvent
      ? {
          name: selectedEvent.name,
          hitsLabel: `${selectedEvent.hits ?? 0}/${selectedEvent.graded_pick_count ?? 0} hits`,
          profitLabel: formatUnits(Number(selectedEvent.total_profit ?? 0)),
        }
      : null,
  }
}

function buildFieldRiskDetail(fieldValidation?: FieldValidation) {
  if (!fieldValidation) {
    return "Field validation not available yet"
  }
  if (fieldValidation.has_cross_tour_field_risk) {
    return "Cross-tour or thin-round validation flags need operator review"
  }
  return "No major field-validation issues are visible in this context"
}

function buildPastMarketLabel(row: PastMarketPredictionRow) {
  if (row.market_family === "matchup") {
    return `${row.player_display ?? "Unknown player"} over ${row.opponent_display ?? "Unknown opponent"}`
  }
  return row.player_display ?? "Unknown player"
}

function countDistinct(values: Array<string | null | undefined>) {
  return new Set(values.filter((value): value is string => Boolean(value && value.trim()))).size
}

function formatSignedNumber(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "Flat"
  }
  return value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1)
}

function formatToParValue(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  if (value === 0) {
    return "E"
  }
  return value > 0 ? `+${value}` : `${value}`
}
