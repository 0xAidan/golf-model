import type { StatusBannerProps } from "@/components/ui/status-banner"
import type { LiveRefreshSnapshot, PredictionRunResponse } from "@/lib/types"

export type WorkspaceBanner = StatusBannerProps & { id: string }

export function buildWorkspaceAlertBanners({
  displayPredictionRun,
  shouldShowOpportunityAlertStrip,
  liveOpportunityAlerts,
  predictionTabPastLoading,
  pastEventName,
  predictionTabPastError,
  pastReplayErrorMessage,
  predictionTabPastNoEvent,
  predictionTabPastPicksLoading,
}: {
  displayPredictionRun: PredictionRunResponse | null
  shouldShowOpportunityAlertStrip: boolean
  liveOpportunityAlerts: NonNullable<
    NonNullable<LiveRefreshSnapshot["live_tournament"]>["live_opportunity_alerts"]
  >
  predictionTabPastLoading: boolean
  pastEventName?: string
  predictionTabPastError: boolean
  pastReplayErrorMessage: string
  predictionTabPastNoEvent?: boolean
  predictionTabPastPicksLoading?: boolean
}) {
  const banners: WorkspaceBanner[] = []

  if (predictionTabPastNoEvent) {
    banners.push({
      id: "past-replay-empty",
      tone: "warn",
      title: "Past replay unavailable",
      message:
        "No completed events are available for replay yet. Once an event finishes and grading runs, it will appear here automatically.",
    })
  }

  const eligibilityWarnings = (displayPredictionRun?.warnings ?? []).filter((warning) =>
    /eligibility|withheld/i.test(warning),
  )
  if (eligibilityWarnings.length > 0) {
    banners.push({
      id: "eligibility-warning-banner",
      tone: "warn",
      title: "Rankings withheld",
      message: eligibilityWarnings.join(" "),
    })
  }

  if (shouldShowOpportunityAlertStrip) {
    banners.push({
      id: "live-opportunity-alert-strip",
      tone: "info",
      title: `${liveOpportunityAlerts.length} new live opportunit${liveOpportunityAlerts.length === 1 ? "y" : "ies"}`,
      message: liveOpportunityAlerts
        .slice(0, 3)
        .map(
          (alert) =>
            `${alert.market_type ?? "market"} · ${alert.player ?? "player"} · ${(Number(alert.ev ?? 0) * 100).toFixed(1)}%`,
        )
        .join(" | "),
    })
  }

  if (predictionTabPastPicksLoading) {
    banners.push({
      id: "past-picks-loading",
      tone: "info",
      title: "Loading graded picks",
      message: `Loading graded picks for ${pastEventName ?? "selected event"}…`,
    })
  }

  if (predictionTabPastLoading) {
    banners.push({
      id: "past-replay-loading",
      tone: "info",
      title: "Loading past replay",
      message: `Loading past tournament replay for ${pastEventName ?? "selected event"}…`,
    })
  }

  if (predictionTabPastError) {
    banners.push({
      id: "past-replay-error",
      tone: "danger",
      title: "Past replay failed",
      message: `${pastReplayErrorMessage}. Try another event or use the Completed lane.`,
    })
  }

  return banners
}
