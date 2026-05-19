import type { ReactNode } from "react"
import { ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"

export function CollapsibleSection({
  title,
  description,
  defaultOpen = false,
  children,
  className,
  testId,
}: {
  title: string
  description?: string
  defaultOpen?: boolean
  children: ReactNode
  className?: string
  testId?: string
}) {
  return (
    <details
      className={cn("collapsible-section", className)}
      open={defaultOpen}
      data-testid={testId}
    >
      <summary className="collapsible-section-summary">
        <span className="collapsible-section-titles">
          <span className="collapsible-section-title">{title}</span>
          {description ? (
            <span className="collapsible-section-desc">{description}</span>
          ) : null}
        </span>
        <ChevronDown size={14} className="collapsible-section-chevron" aria-hidden />
      </summary>
      <div className="collapsible-section-body">{children}</div>
    </details>
  )
}
