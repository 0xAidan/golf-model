import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type PanelBackfillProps = {
  message?: string
  detail?: ReactNode
  loading?: boolean
  className?: string
  testId?: string
}

export function PanelBackfill({
  message = "Waiting for data",
  detail,
  loading = true,
  className,
  testId = "monitoring-panel-backfill",
}: PanelBackfillProps) {
  return (
    <div
      className={cn("monitoring-panel-backfill", className)}
      data-testid={testId}
      role={loading ? "status" : undefined}
      aria-busy={loading}
    >
      {loading ? <div className="monitoring-panel-backfill__pulse" aria-hidden /> : null}
      <p>{message}</p>
      {detail ? <div className="text-[var(--text-xs)]">{detail}</div> : null}
    </div>
  )
}
