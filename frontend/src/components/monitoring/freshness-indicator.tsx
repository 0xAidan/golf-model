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
  /** Extra lines shown in the header popover (snapshot age, heartbeat, etc.) */
  detailLines?: string[]
  variant?: "default" | "compact"
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
  detailLines,
  variant = "default",
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
  const showDetails = (detailLines?.length ?? 0) > 0 || state === "error" || state === "stale"

  const chipBody = (
    <>
      {state === "updating" ? (
        <RefreshCw className="freshness-indicator__spin" size={12} aria-hidden />
      ) : (
        <span className="freshness-indicator__dot" aria-hidden />
      )}
      <span className="freshness-indicator__label">{label}</span>
    </>
  )

  if (variant === "compact" && showDetails) {
    return (
      <details
        className={cn(
          "freshness-indicator freshness-indicator--compact",
          `freshness-indicator--${tone}`,
          className,
        )}
        data-testid="freshness-indicator"
        data-state={state}
      >
        <summary className="freshness-indicator__summary" aria-live="polite">
          {chipBody}
        </summary>
        <div className="freshness-indicator__popover" role="status">
          {detailLines?.map((line) => (
            <p key={line} className="freshness-indicator__detail-line">
              {line}
            </p>
          ))}
          <Link to="/system" className="freshness-indicator__details link-subtle">
            Open System
          </Link>
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
      </details>
    )
  }

  return (
    <div
      className={cn(
        "freshness-indicator",
        variant === "compact" && "freshness-indicator--compact",
        `freshness-indicator--${tone}`,
        className,
      )}
      data-testid="freshness-indicator"
      data-state={state}
      role="status"
      aria-live="polite"
    >
      {chipBody}
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
