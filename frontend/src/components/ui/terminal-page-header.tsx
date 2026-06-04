import type { ReactNode } from "react"

import { PageHeader } from "@/components/ui/page-header"
import { cn } from "@/lib/utils"

export function TerminalPageHeader({
  eyebrow,
  title,
  description,
  action,
  kpis,
  className,
}: {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
  kpis?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("terminal-page-header", className)}>
      <PageHeader eyebrow={eyebrow} title={title} description={description} action={action} />
      {kpis ? <div className="terminal-page-header-kpis">{kpis}</div> : null}
    </div>
  )
}
