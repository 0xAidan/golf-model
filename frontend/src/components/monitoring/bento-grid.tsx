import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type BentoGridProps = {
  children: ReactNode
  columns?: 1 | 2 | 3 | 12
  className?: string
  testId?: string
}

export function BentoGrid({
  children,
  columns = 12,
  className,
  testId = "monitoring-bento-grid",
}: BentoGridProps) {
  return (
    <div
      className={cn(
        "monitoring-bento-grid",
        columns === 1 && "monitoring-bento-grid--cols-1",
        columns === 2 && "monitoring-bento-grid--cols-2",
        columns === 3 && "monitoring-bento-grid--cols-3",
        className,
      )}
      data-testid={testId}
    >
      {children}
    </div>
  )
}
