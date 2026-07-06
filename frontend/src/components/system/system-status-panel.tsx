import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type SystemStatusTone = "good" | "warn" | "bad"

const toneClasses: Record<SystemStatusTone, string> = {
  good: "border-[var(--green)]/40 bg-[var(--green-bg)]/30 text-[var(--green)]",
  warn: "border-[var(--amber)]/40 bg-[var(--amber-bg)]/30 text-[var(--amber)]",
  bad: "border-[var(--red)]/40 bg-[var(--red-bg)]/30 text-[var(--red)]",
}

const toneLabels: Record<SystemStatusTone, string> = {
  good: "Healthy",
  warn: "Watch",
  bad: "Action needed",
}

export function SystemStatusPanel({
  title,
  tone,
  summary,
  detail,
  action,
  children,
  testId,
}: {
  title: string
  tone: SystemStatusTone
  summary: string
  detail?: string
  action?: ReactNode
  children?: ReactNode
  testId?: string
}) {
  return (
    <section
      className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
      data-testid={testId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
            <span
              className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", toneClasses[tone])}
            >
              {toneLabels[tone]}
            </span>
          </div>
          <p className="text-sm text-[var(--text-primary)]">{summary}</p>
          {detail ? <p className="text-xs text-[var(--text-secondary)]">{detail}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children ? <div className="mt-3 border-t border-[var(--border)] pt-3">{children}</div> : null}
    </section>
  )
}
