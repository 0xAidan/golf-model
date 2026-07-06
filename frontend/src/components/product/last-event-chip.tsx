import { CheckCircle2, Clock3 } from "lucide-react"
import { Link } from "react-router-dom"

import { cn } from "@/lib/utils"

export const LastEventChip = ({
  eventName,
  gradedCount,
  ungradedPositiveEvCount,
  className,
}: {
  eventName?: string | null
  gradedCount?: number
  ungradedPositiveEvCount?: number
  className?: string
}) => {
  if (!eventName) {
    return (
      <Link
        to="/results"
        className={cn("last-event-chip last-event-chip--empty", className)}
        data-testid="last-event-chip"
      >
        <span className="last-event-chip__eyebrow">Last event</span>
        <span className="last-event-chip__summary">No graded event yet</span>
      </Link>
    )
  }

  const graded = Number(gradedCount ?? 0)
  const ungraded = Number(ungradedPositiveEvCount ?? 0)
  const isWarn = ungraded > 0

  return (
    <Link
      to="/results"
      className={cn("last-event-chip", isWarn && "last-event-chip--warn", className)}
      data-testid="last-event-chip"
    >
      <span className="last-event-chip__eyebrow">Last event</span>
      <span className="last-event-chip__title" title={eventName}>
        {eventName}
      </span>
      <span className="last-event-chip__summary">
        <span className="last-event-chip__metric">
          <CheckCircle2 size={12} aria-hidden />
          {graded} graded
        </span>
        <span className="last-event-chip__divider" aria-hidden>
          ·
        </span>
        <span className="last-event-chip__metric">
          <Clock3 size={12} aria-hidden />
          {ungraded > 0 ? `${ungraded} ungraded` : "all graded"}
        </span>
      </span>
    </Link>
  )
}
