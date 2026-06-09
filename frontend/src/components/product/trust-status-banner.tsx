import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react"

import { cn } from "@/lib/utils"

export type TrustTone = "healthy" | "warn" | "danger" | "neutral"

export const TrustStatusBanner = ({
  tone = "neutral",
  title,
  message,
  testId = "trust-status-banner",
}: {
  tone?: TrustTone
  title?: string
  message: string
  testId?: string
}) => {
  const Icon =
    tone === "healthy"
      ? CheckCircle2
      : tone === "danger"
        ? ShieldAlert
        : tone === "warn"
          ? AlertTriangle
          : Info

  return (
    <div
      className={cn(
        "trust-status-banner",
        tone === "healthy" && "trust-status-banner--healthy",
        tone === "warn" && "trust-status-banner--warn",
        tone === "danger" && "trust-status-banner--danger",
      )}
      role="status"
      aria-live="polite"
      data-testid={testId}
    >
      <Icon size={16} aria-hidden className="shrink-0" />
      <div>
        {title ? <strong className="mr-2">{title}</strong> : null}
        <span>{message}</span>
      </div>
    </div>
  )
}
