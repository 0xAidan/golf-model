import { cn } from "@/lib/utils"

export type MonitoringTickerItem = {
  id: string
  text: string
}

export type MonitoringTickerProps = {
  items: MonitoringTickerItem[]
  className?: string
  testId?: string
}

export function MonitoringTicker({ items, className, testId = "monitoring-ticker" }: MonitoringTickerProps) {
  if (items.length === 0) return null

  const doubled = [...items, ...items]

  return (
    <div className={cn("monitoring-ticker", className)} data-testid={testId} aria-live="polite">
      <div className="monitoring-ticker__track">
        {doubled.map((item, index) => (
          <span key={`${item.id}-${index}`} className="monitoring-ticker__item">
            {item.text}
          </span>
        ))}
      </div>
    </div>
  )
}
