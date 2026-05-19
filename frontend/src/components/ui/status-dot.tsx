import { cn } from "@/lib/utils"

export type StatusDotTone = "good" | "warn" | "bad" | "muted" | "live"

export function StatusDot({
  tone,
  pulse = false,
  className,
  label,
}: {
  tone: StatusDotTone
  pulse?: boolean
  className?: string
  /** Accessible name when dot is standalone */
  label?: string
}) {
  return (
    <span
      className={cn("status-dot", `status-dot--${tone}`, pulse && "status-dot--pulse", className)}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  )
}
