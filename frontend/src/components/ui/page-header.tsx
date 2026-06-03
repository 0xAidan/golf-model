import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function PageHeader({
  title,
  description,
  action,
  titleId,
  className,
  eyebrow,
}: {
  title: string
  description?: string
  action?: ReactNode
  titleId?: string
  className?: string
  eyebrow?: string
}) {
  return (
    <header className={cn("page-header", className)}>
      <div className="page-header-text">
        {eyebrow ? <p className="page-header-eyebrow">{eyebrow}</p> : null}
        <h1 className="page-header-title" id={titleId}>
          {title}
        </h1>
        {description ? <p className="page-header-desc">{description}</p> : null}
      </div>
      {action ? <div className="page-header-action">{action}</div> : null}
    </header>
  )
}
