import { AlertTriangle } from "lucide-react"

import { cn } from "@/lib/utils"

export const shouldShowRebuildBanner = ({
  dbOk,
  rebuildState,
}: {
  dbOk: boolean | null
  rebuildState: string | null
}): boolean => dbOk === false || rebuildState === "rebuilding"

export const RebuildStatusBanner = ({
  message,
  title = "Boards may be out of date",
}: {
  message: string
  title?: string
}) => {
  return (
    <div
      className={cn(
        "mx-auto mb-3 w-full max-w-[1600px] rounded-md border border-amber-500/60",
        "bg-amber-500/15 px-4 py-3 text-sm text-amber-100",
      )}
      role="alert"
      aria-live="assertive"
      tabIndex={0}
      data-testid="rebuild-status-banner"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={20} aria-hidden className="mt-0.5 shrink-0" />
        <div>
          <strong className="block text-base text-amber-50">{title}</strong>
          <p className="mt-1 text-amber-100/90">{message}</p>
        </div>
      </div>
    </div>
  )
}
