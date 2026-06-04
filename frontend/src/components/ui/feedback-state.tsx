import type { ReactNode } from "react"

import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export function LoadingState({
  message = "Loading…",
  className,
}: {
  message?: string
  className?: string
}) {
  return (
    <div
      className={cn("feedback-state feedback-state--loading", className)}
      role="status"
      aria-live="polite"
      data-testid="loading-state"
    >
      <div className="feedback-state-skeletons" aria-hidden="true">
        <Skeleton className="feedback-skeleton-row" />
        <Skeleton className="feedback-skeleton-row" />
        <Skeleton className="feedback-skeleton-row" />
      </div>
      <span className="feedback-state-message">{message}</span>
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      className={cn("feedback-state feedback-state--error", className)}
      role="alert"
      data-testid="error-state"
    >
      <p className="feedback-state-message">{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn-ghost btn-compact" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}

export { EmptyState } from "@/components/ui/empty-state"

export function PageSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="page-skeleton" data-testid="page-skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="page-skeleton-row" />
      ))}
    </div>
  )
}

export type FeedbackIconProps = { icon?: ReactNode }
