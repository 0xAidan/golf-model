import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type FeedItemProps = {
  time?: string
  children: ReactNode
  className?: string
  testId?: string
}

export function FeedItem({ time, children, className, testId }: FeedItemProps) {
  return (
    <li className={cn("monitoring-feed-item", className)} data-testid={testId}>
      {time ? <time className="monitoring-feed-item__time">{time}</time> : null}
      <span className="monitoring-feed-item__body">{children}</span>
    </li>
  )
}
