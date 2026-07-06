import type { ReactNode } from "react"
import { AlertCircle, AlertTriangle, Info } from "lucide-react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type StatusBannerTone = "info" | "warn" | "danger"

export type StatusBannerProps = {
  tone: StatusBannerTone
  title: string
  message: string
  action?: { label: string; onClick: () => void }
  systemLink?: boolean
  className?: string
}

const toneIcon = (tone: StatusBannerTone) => {
  switch (tone) {
    case "info":
      return Info
    case "warn":
      return AlertTriangle
    case "danger":
      return AlertCircle
    default: {
      const _exhaustive: never = tone
      return _exhaustive
    }
  }
}

export function StatusBanner({
  tone,
  title,
  message,
  action,
  systemLink = false,
  className,
}: StatusBannerProps) {
  const Icon = toneIcon(tone)

  return (
    <div
      className={cn("status-banner", `status-banner--${tone}`, className)}
      role="status"
      data-testid="status-banner"
      data-tone={tone}
    >
      <Icon className="status-banner__icon" size={16} aria-hidden />
      <div className="status-banner__body">
        <p className="status-banner__title">{title}</p>
        <p className="status-banner__message">{message}</p>
      </div>
      <div className="status-banner__actions">
        {action ? (
          <Button type="button" variant="outline" size="xs" onClick={action.onClick}>
            {action.label}
          </Button>
        ) : null}
        {systemLink ? (
          <Link to="/system" className="status-banner__system-link link-subtle">
            Details → System
          </Link>
        ) : null}
      </div>
    </div>
  )
}

export type StatusBannerStackProps = {
  banners: Array<StatusBannerProps & { id: string }>
  className?: string
}

/** Highest-severity banner wins; additional banners collapse behind "+ n more". */
export function StatusBannerStack({ banners, className }: StatusBannerStackProps) {
  if (banners.length === 0) return null

  const severity: Record<StatusBannerTone, number> = { danger: 3, warn: 2, info: 1 }
  const sorted = [...banners].sort((a, b) => severity[b.tone] - severity[a.tone])
  const primary = sorted[0]
  const overflow = sorted.slice(1)

  if (!primary) return null

  return (
    <div className={cn("status-banner-stack", className)} data-testid="status-banner-stack">
      <StatusBanner {...primary} />
      {overflow.length > 0 ? (
        <details className="status-banner-stack__more">
          <summary className="status-banner-stack__more-summary">+ {overflow.length} more</summary>
          <div className="status-banner-stack__more-list">
            {overflow.map((banner) => (
              <StatusBanner key={banner.id} {...banner} />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}
