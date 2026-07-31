import type { ReactNode } from "react"

export function PageHeader({
  eyebrow,
  title,
  detail,
  actions,
}: {
  eyebrow: string
  title: string
  detail?: string
  actions?: ReactNode
}) {
  return (
    <header className="flex min-h-14 flex-col gap-3 border-b border-slate-800 pb-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">{eyebrow}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-white">{title}</h1>
        {detail ? <p className="mt-1 text-sm text-slate-400">{detail}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  )
}
