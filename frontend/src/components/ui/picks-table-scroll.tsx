import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/** Scroll region with sticky terminal table headers for picks/matchup boards. */
export function PicksTableScroll({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={cn("table-scroll-region picks-table-scroll", className)}>{children}</div>
}
