import type { ReactNode } from "react"

import { ModelLaneBadge, type ModelLane } from "@/components/product/model-lane-badge"
import { cn } from "@/lib/utils"

export const EventCommandHeader = ({
  lane,
  meta,
  trailing,
  className,
}: {
  lane: ModelLane
  meta?: string
  trailing?: ReactNode
  className?: string
}) => (
  <header className={cn("event-command-header", className)} data-testid="event-command-header">
    <div className="event-command-header__primary">
      <div className="flex flex-wrap items-center gap-2">
        <ModelLaneBadge lane={lane} />
      </div>
      {meta ? <p className="event-command-header__meta">{meta}</p> : null}
    </div>
    {trailing ? <div className="event-command-header__trailing">{trailing}</div> : null}
  </header>
)
