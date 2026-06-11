import type { ReactNode } from "react"

import { ModelLaneBadge, type ModelLane } from "@/components/product/model-lane-badge"
import { cn } from "@/lib/utils"

export type EventCommandKpi = {
  id: string
  label: string
  value: string
  tone?: "positive" | "negative" | "neutral"
}

export const EventCommandHeader = ({
  lane,
  eventName,
  meta,
  kpis = [],
  trailing,
  className,
}: {
  lane: ModelLane
  eventName: string
  meta?: string
  kpis?: EventCommandKpi[]
  trailing?: ReactNode
  className?: string
}) => (
  <header className={cn("event-command-header", className)} data-testid="event-command-header">
    <div className="event-command-header__primary">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <ModelLaneBadge lane={lane} />
      </div>
      <h1 className="event-command-header__event" title={eventName}>
        {eventName}
      </h1>
      {meta ? <p className="event-command-header__meta">{meta}</p> : null}
    </div>
    {kpis.length > 0 ? (
      <div className="event-command-header__kpis" data-testid="event-command-kpis">
        {kpis.map((kpi) => (
          <div key={kpi.id} className="event-command-kpi">
            <div className="event-command-kpi__label">{kpi.label}</div>
            <div
              className={cn(
                "event-command-kpi__value",
                kpi.tone === "positive" && "metric--positive",
                kpi.tone === "negative" && "metric--negative",
              )}
            >
              {kpi.value}
            </div>
          </div>
        ))}
      </div>
    ) : null}
    {trailing}
  </header>
)
