import { Radar } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { LiveRefreshSnapshot, PredictionRunResponse } from "@/lib/types"

export function WorkspaceAlerts({
  snapshotNotice,
  snapshotDataState,
  onRecoverStaleData,
  recoverStalePending = false,
  displayPredictionRun,
  shouldShowOpportunityAlertStrip,
  liveOpportunityAlerts,
  liveSnapshot,
  onDismissOpportunityAlerts,
  predictionTabPastLoading,
  pastEventName,
  predictionTabPastError,
  pastReplayErrorMessage,
}: {
  snapshotNotice: string | null
  snapshotDataState?: string | null
  onRecoverStaleData?: () => void
  recoverStalePending?: boolean
  displayPredictionRun: PredictionRunResponse | null
  shouldShowOpportunityAlertStrip: boolean
  liveOpportunityAlerts: NonNullable<
    NonNullable<LiveRefreshSnapshot["live_tournament"]>["live_opportunity_alerts"]
  >
  liveSnapshot: LiveRefreshSnapshot | null
  onDismissOpportunityAlerts: () => void
  predictionTabPastLoading: boolean
  pastEventName?: string
  predictionTabPastError: boolean
  pastReplayErrorMessage: string
}) {
  return (
    <>
      {snapshotNotice ? (
        <div className="alert-banner" role="status" aria-live="polite">
          <Radar size={11} style={{ flexShrink: 0 }} />
          <span className="min-w-0 flex-1">{snapshotNotice}</span>
          {snapshotDataState === "stale" && onRecoverStaleData ? (
            <Button
              type="button"
              size="xs"
              variant="secondary"
              className="shrink-0"
              disabled={recoverStalePending}
              onClick={onRecoverStaleData}
              aria-label="Recover stale live data"
            >
              {recoverStalePending ? "Recovering…" : "Recover now"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {displayPredictionRun?.hydration_section === "upcoming_fallback_live" ||
      displayPredictionRun?.hydration_section === "live_fallback_upcoming" ? (
        <div
          className="alert-banner alert-banner--warn"
          role="status"
          data-testid="hydration-fallback-banner"
        >
          {displayPredictionRun.hydration_section === "upcoming_fallback_live"
            ? "Upcoming view is showing live snapshot data — upcoming section unavailable."
            : "Live view is showing upcoming snapshot data — live section unavailable."}
        </div>
      ) : null}
      {(displayPredictionRun?.warnings ?? []).some((w) => /eligibility|withheld/i.test(w)) ? (
        <div
          className="alert-banner alert-banner--warn"
          role="status"
          data-testid="eligibility-warning-banner"
        >
          {(displayPredictionRun?.warnings ?? [])
            .filter((w) => /eligibility|withheld/i.test(w))
            .join(" ")}
        </div>
      ) : null}
      {shouldShowOpportunityAlertStrip ? (
        <div
          className="alert-banner alert-banner--opportunity"
          role="status"
          aria-live="polite"
          data-testid="live-opportunity-alert-strip"
        >
          <span className="live-opportunity-banner-title">
            {liveOpportunityAlerts.length} new live opportunit
            {liveOpportunityAlerts.length === 1 ? "y" : "ies"}
          </span>
          <span className="live-opportunity-banner-list">
            {liveOpportunityAlerts
              .slice(0, 3)
              .map((alert) =>
                `${alert.market_type ?? "market"} · ${alert.player ?? "player"} · ${(Number(alert.ev ?? 0) * 100).toFixed(1)}%`,
              )
              .join(" | ")}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-compact"
            onClick={onDismissOpportunityAlerts}
            aria-label="Dismiss live opportunity alerts"
          >
            Dismiss
          </button>
        </div>
      ) : null}
      {predictionTabPastLoading ? (
        <div className="alert-banner" role="status" aria-live="polite" data-testid="past-replay-loading">
          Loading past tournament replay for {pastEventName ?? "selected event"}…
        </div>
      ) : null}
      {predictionTabPastError ? (
        <div className="alert-banner" role="alert" data-testid="past-replay-error">
          Past replay failed: {pastReplayErrorMessage}. Try another event or use the Completed lane.
        </div>
      ) : null}
    </>
  )
}
