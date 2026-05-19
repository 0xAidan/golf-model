import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function SectionHeader({
  title,
  description,
  action,
  titleId,
  className,
}: {
  title: string
  description?: string
  action?: ReactNode
  titleId?: string
  className?: string
}) {
  return (
    <div className={cn("section-header", className)}>
      <div>
        <div className="section-title" id={titleId}>
          {title}
        </div>
        {description ? <div className="section-desc">{description}</div> : null}
      </div>
      {action}
    </div>
  )
}
