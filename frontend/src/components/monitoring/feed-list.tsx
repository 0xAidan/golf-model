import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type FeedListProps = {
  children: ReactNode
  className?: string
  testId?: string
  "aria-label"?: string
}

export function FeedList({
  children,
  className,
  testId = "monitoring-feed-list",
  "aria-label": ariaLabel = "Activity feed",
}: FeedListProps) {
  return (
    <ul className={cn("monitoring-feed-list", className)} data-testid={testId} aria-label={ariaLabel}>
      {children}
    </ul>
  )
}
