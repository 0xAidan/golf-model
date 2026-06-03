import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function PanelChrome({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn("panel-chrome", className)}>
      <div className="panel-chrome-header">
        <div>
          <div className="panel-chrome-title">{title}</div>
          {description ? <div className="collapsible-section-desc">{description}</div> : null}
        </div>
        {action}
      </div>
      <div className="panel-chrome-body">{children}</div>
    </div>
  )
}
