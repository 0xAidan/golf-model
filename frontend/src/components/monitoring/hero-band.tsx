import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type HeroBandProps = {
  title: string
  eyebrow?: string
  meta?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
  testId?: string
}

export function HeroBand({
  title,
  eyebrow,
  meta,
  action,
  children,
  className,
  testId = "monitoring-hero-band",
}: HeroBandProps) {
  return (
    <section className={cn("monitoring-hero-band", className)} data-testid={testId}>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {eyebrow ? <p className="monitoring-hero-band__eyebrow">{eyebrow}</p> : null}
        <h1 className="monitoring-hero-band__title">{title}</h1>
        {meta ? <div className="text-[var(--text-sm)] text-[var(--text-secondary)]">{meta}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
      {children}
    </section>
  )
}
