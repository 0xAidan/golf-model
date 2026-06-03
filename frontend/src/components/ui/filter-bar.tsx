import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function FilterBar({
  children,
  className,
  "aria-label": ariaLabel = "Filters",
}: {
  children: ReactNode
  className?: string
  "aria-label"?: string
}) {
  return (
    <div className={cn("filter-bar", className)} role="toolbar" aria-label={ariaLabel}>
      {children}
    </div>
  )
}
