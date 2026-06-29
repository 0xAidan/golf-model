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
