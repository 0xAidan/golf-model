import type { ReactNode } from "react"

export function PageHeader({
  eyebrow,
  title,
  detail,
  meta,
  actions,
}: {
  eyebrow: string
  title: string
  detail?: string
  meta?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="op-eyebrow text-[var(--op-accent)]">{eyebrow}</p>
        <h1 className="mt-1.5 truncate text-[28px] font-semibold leading-none tracking-tight text-white">{title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-[var(--op-text-secondary)]">
          {detail ? <span>{detail}</span> : null}
          {meta}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  )
}
