import { Link } from "react-router-dom"
import { RefreshCw } from "lucide-react"

import { deriveFreshnessState, freshnessLabel, type FreshnessState } from "@/lib/freshness-state"
import { formatAgeLabel } from "@/lib/snapshot-chip"
import { cn } from "@/lib/utils"

export type FreshnessIndicatorProps = {
  dataState?: string | null
  ageSeconds?: number | null
  staleAfterSeconds?: number | null
  isFetching: boolean
  refreshQueued?: boolean
  isOnline?: boolean
  isError?: boolean
  splitBrain?: boolean
  onRetry?: () => void
  onRefresh?: () => void
  className?: string
}

const toneForState = (state: FreshnessState): "good" | "warn" | "bad" => {
  switch (state) {
    case "fresh":
      return "good"
    case "updating":
    case "stale":
      return "warn"
    case "offline":
    case "error":
      return "bad"
    default: {
      const _exhaustive: never = state
      return _exhaustive
    }
  }
}

export function FreshnessIndicator({
  dataState,
  ageSeconds = null,
  staleAfterSeconds = null,
  isFetching,
  refreshQueued = false,
  isOnline = typeof navigator !== "undefined" ? navigator.onLine : true,
  isError = false,
  splitBrain = false,
  onRetry,
  onRefresh,
  className,
}: FreshnessIndicatorProps) {
  const state = deriveFreshnessState({
    dataState,
    ageSeconds,
    staleAfterSeconds,
    isFetching,
    refreshQueued,
    isOnline,
    isError,
    splitBrain,
  })
  const tone = toneForState(state)
  const label = freshnessLabel(state, ageSeconds, formatAgeLabel)

  return (
    <div
      className={cn("freshness-indicator", `freshness-indicator--${tone}`, className)}
      data-testid="freshness-indicator"
      data-state={state}
      role="status"
      aria-live="polite"
    >
      {state === "updating" ? (
        <RefreshCw className="freshness-indicator__spin" size={12} aria-hidden />
      ) : (
        <span className="freshness-indicator__dot" aria-hidden />
      )}
      <span className="freshness-indicator__label">{label}</span>
      {state === "error" ? (
        <Link to="/system" className="freshness-indicator__details link-subtle">
          Details
        </Link>
      ) : null}
      {onRetry && (state === "error" || state === "offline") ? (
        <button type="button" className="btn btn-ghost btn-xs" onClick={onRetry}>
          Retry
        </button>
      ) : null}
      {onRefresh && state === "stale" ? (
        <button type="button" className="btn btn-ghost btn-xs" onClick={onRefresh}>
          Refresh
        </button>
      ) : null}
    </div>
  )
}
