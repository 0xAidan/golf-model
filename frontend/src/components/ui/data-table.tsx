import type { HTMLAttributes, ReactNode, TableHTMLAttributes } from "react"
import { cn } from "@/lib/utils"

export function DataTable({
  children,
  className,
  tableClassName,
  stickyHeader = true,
  ...scrollProps
}: {
  children: ReactNode
  className?: string
  tableClassName?: string
  stickyHeader?: boolean
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("table-scroll-region", className)} {...scrollProps}>
      <table
        className={cn(
          "data-table",
          stickyHeader && "terminal-table",
          tableClassName,
        )}
      >
        {children}
      </table>
    </div>
  )
}

export function DataTableRoot({
  className,
  ...props
}: TableHTMLAttributes<HTMLTableElement>) {
  return <table className={cn("data-table", "terminal-table", className)} {...props} />
}
