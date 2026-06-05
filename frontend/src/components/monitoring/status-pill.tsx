import { cn } from "@/lib/utils"

export type MonitoringStatus = "live" | "warn" | "idle" | "error"

export type StatusPillProps = {
  status: MonitoringStatus
  label: string
  className?: string
  testId?: string
}

export function StatusPill({ status, label, className, testId = "monitoring-status-pill" }: StatusPillProps) {
  return (
    <span
      className={cn(
        "monitoring-status-pill",
        status === "live" && "monitoring-status-pill--live",
        status === "warn" && "monitoring-status-pill--warn",
        status === "idle" && "monitoring-status-pill--idle",
        status === "error" && "monitoring-status-pill--error",
        className,
      )}
      data-testid={testId}
      data-status={status}
    >
      <span className="monitoring-status-pill__dot" aria-hidden />
      {label}
    </span>
  )
}
