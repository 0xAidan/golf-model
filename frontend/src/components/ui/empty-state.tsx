import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function EmptyState({
  message,
  description,
  icon,
  className,
}: {
  message: string
  description?: string
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("empty-state", className)}>
      {icon ? <div className="empty-state-icon">{icon}</div> : null}
      <div className="empty-state-title">{message}</div>
      {description ? <div className="empty-state-desc">{description}</div> : null}
    </div>
  )
}
