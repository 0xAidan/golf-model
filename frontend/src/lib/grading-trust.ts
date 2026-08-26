import type {
  DashboardState,
  GradedTournamentSummary,
  GradingHistoryResponse,
  GradingSeasonResponse,
  LiveRefreshRuntimeStatus,
} from "@/lib/types"

import {
  pickLatestGradedSeasonEvent,
  seasonLaneFromPickSource,
  sumUngradedPositiveEvForCompletedEvents,
} from "@/lib/grading-season"

export type GradingTrustMetrics = {
  lastGradedAt: string | null
  positiveEvPickCount: number
  ungradedPositiveEvCount: number
  showUngradedBanner: boolean
  autoGradeMessage: string | null
}

function countPositiveEvPicks(tournaments: GradedTournamentSummary[]): number {
  let total = 0
  for (const event of tournaments) {
    for (const pick of event.picks ?? []) {
      const ev = pick.ev
      if (ev != null && ev > 0) total += 1
    }
  }
  return total
}

export type AutoGradeStatusPayload = Record<string, unknown> | string | null | undefined

const asAutoGradeObject = (
  autoGrade: AutoGradeStatusPayload,
): Record<string, unknown> | null => {
  if (autoGrade == null) return null
  if (typeof autoGrade === "string") {
    const trimmed = autoGrade.trim()
    return trimmed ? { status: trimmed } : null
  }
  if (typeof autoGrade !== "object") return null
  return autoGrade
}

/**
 * Operator-facing last-auto-grade label. Never String(object).
 * Accepts the production object payload or a legacy string.
 */
export const formatAutoGradeStatusLabel = (
  autoGrade: AutoGradeStatusPayload,
): string | null => {
  const payload = asAutoGradeObject(autoGrade)
  if (!payload) return null

  const status = String(payload.status ?? "").trim().toLowerCase()
  const reason = String(payload.reason ?? "").trim()
  const message = String(payload.message ?? "").trim()

  if (status === "error") {
    return message || "Auto-grade failed — use Grade event or check backend logs."
  }
  if (status === "captured" && reason === "awaiting_results") {
    return "waiting for Data Golf final results"
  }
  if (status === "skipped" && reason === "no_inventory") {
    return "skipped: no pick inventory"
  }
  if (status === "skipped" && reason === "already_graded") {
    return "already graded"
  }
  if (status === "skipped" && reason === "awaiting_retry_scheduled") {
    return "waiting to retry"
  }
  if (status === "skipped" && reason === "awaiting_retry_window_expired") {
    return "retry window expired"
  }
  if (status === "skipped" && reason === "no_tracked_picks") {
    return "skipped: no tracked picks"
  }
  if (status === "skipped" && reason === "event_not_gradeable") {
    return "skipped: event not gradeable"
  }
  if (status === "complete") return "complete"
  if (status === "partial") return reason ? `partial (${reason})` : "partial"
  if (status === "ok") return "complete"
  if (status === "skipped") return reason ? `skipped (${reason})` : "skipped"
  if (status) return reason ? `${status} (${reason})` : status
  if (message) return message
  return null
}

const formatAutoGradeMessage = (
  liveRefreshStatus: LiveRefreshRuntimeStatus | undefined,
): string | null => {
  const autoGrade = liveRefreshStatus?.last_auto_grade_status
  if (!autoGrade || typeof autoGrade !== "object") return null

  const status = String(autoGrade.status ?? "").trim().toLowerCase()
  const reason = String(autoGrade.reason ?? "").trim()

  if (status === "error") {
    return String(autoGrade.message ?? "Auto-grade failed — use Grade event or check backend logs.")
  }
  if (status === "captured" && reason === "awaiting_results") {
    return "Auto-grade waiting for Data Golf final results — will retry automatically."
  }
  if (status === "skipped" && reason === "no_inventory") {
    return "Auto-grade skipped: no pick inventory captured for the completed event."
  }
  if (status === "skipped" && reason === "already_graded") {
    return null
  }
  return null
}

/**
 * Trust strip metrics for /grading and /track-record.
 * +EV-only: ungraded counts come from season lane data for completed events only.
 */
export function buildGradingTrustMetrics(
  history: GradingHistoryResponse | undefined,
  dashboard: DashboardState | undefined,
  liveRefreshStatus?: LiveRefreshRuntimeStatus,
  season?: GradingSeasonResponse,
  pickSource: "all" | "cockpit" | "lab" = "cockpit",
): GradingTrustMetrics {
  const tournaments = history?.tournaments ?? []
  const summaryPicks = history?.summary?.combined?.picks
  const positiveEvPickCount =
    summaryPicks != null && summaryPicks > 0
      ? summaryPicks
      : countPositiveEvPicks(tournaments)

  const latestFromSeason = season
    ? pickLatestGradedSeasonEvent(season.events, pickSource)
    : null
  const lastGradedAt =
    latestFromSeason?.last_graded_at ??
    tournaments
      .map((event) => event.last_graded_at)
      .filter(Boolean)
      .sort((left, right) => Date.parse(String(right)) - Date.parse(String(left)))[0] ??
    dashboard?.latest_graded_tournament?.last_graded_at ??
    null

  const ungradedPositiveEvCount = season
    ? sumUngradedPositiveEvForCompletedEvents(season.events, pickSource)
    : 0

  return {
    lastGradedAt,
    positiveEvPickCount,
    ungradedPositiveEvCount,
    showUngradedBanner: ungradedPositiveEvCount > 0,
    autoGradeMessage: formatAutoGradeMessage(liveRefreshStatus),
  }
}
