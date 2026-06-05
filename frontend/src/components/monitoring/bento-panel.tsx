import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type BentoPanelSpan = 4 | 6 | 8 | 12

export type BentoPanelProps = {
  title?: string
  action?: ReactNode
  children: ReactNode
  span?: BentoPanelSpan
  rowSpan?: 1 | 2
  className?: string
  testId?: string
}

export function BentoPanel({
  title,
  action,
  children,
  span = 12,
  rowSpan = 1,
  className,
  testId = "monitoring-bento-panel",
}: BentoPanelProps) {
  return (
    <section
      className={cn(
        "monitoring-bento-panel monitor-lane",
        span === 4 && "monitoring-bento-panel--span-4",
        span === 6 && "monitoring-bento-panel--span-6",
        span === 8 && "monitoring-bento-panel--span-8",
        span === 12 && "monitoring-bento-panel--span-12",
        rowSpan === 2 && "monitoring-bento-panel--row-2",
        className,
      )}
      data-testid={testId}
    >
      {title || action ? (
        <header className="monitoring-bento-panel__header">
          {title ? <h2 className="monitoring-bento-panel__title">{title}</h2> : <span />}
          {action}
        </header>
      ) : null}
      <div className="monitoring-bento-panel__body monitor-panel-scroll">{children}</div>
    </section>
  )
}
