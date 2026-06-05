import type { DashboardState, GradedTournamentSummary, GradingHistoryResponse } from "@/lib/types"

export type GradingTrustMetrics = {
  lastGradedAt: string | null
  positiveEvPickCount: number
  ungradedPositiveEvCount: number
  showUngradedBanner: boolean
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

function ungradedFromTournament(row: GradedTournamentSummary | null | undefined): number {
  if (!row) return 0
  const picks = row.picks_count ?? 0
  const graded = row.graded_pick_count ?? 0
  return Math.max(0, picks - graded)
}

/**
 * Trust strip metrics for /grading and /track-record.
 * +EV-only: persisted picks are already ev > 0; ungraded gap uses pick vs outcome counts.
 */
export function buildGradingTrustMetrics(
  history: GradingHistoryResponse | undefined,
  dashboard: DashboardState | undefined,
): GradingTrustMetrics {
  const tournaments = history?.tournaments ?? []
  const summaryPicks = history?.summary?.combined?.picks
  const positiveEvPickCount =
    summaryPicks != null && summaryPicks > 0
      ? summaryPicks
      : countPositiveEvPicks(tournaments)

  const lastGradedAt =
    tournaments[0]?.last_graded_at ??
    dashboard?.latest_graded_tournament?.last_graded_at ??
    null

  const latestGradedGap = ungradedFromTournament(dashboard?.latest_graded_tournament)
  const completedEvent = dashboard?.latest_completed_event
  const gradedEventId = dashboard?.latest_graded_tournament?.event_id
  const completedNeedsGrade =
    completedEvent?.event_id &&
    completedEvent.event_id !== gradedEventId &&
    latestGradedGap === 0

  const ungradedPositiveEvCount = completedNeedsGrade
    ? Math.max(latestGradedGap, 1)
    : latestGradedGap

  return {
    lastGradedAt,
    positiveEvPickCount,
    ungradedPositiveEvCount,
    showUngradedBanner: ungradedPositiveEvCount > 0,
  }
}
