import type { ReactNode } from "react"
import { useLocation } from "react-router-dom"

import { RouteErrorBoundary } from "@/components/route-error-boundary"

type RouteErrorBoundaryGateProps = {
  children: ReactNode
  track?: string | null
  mode?: string | null
  snapshotId?: string | null
}

export function RouteErrorBoundaryGate({
  children,
  track,
  mode,
  snapshotId,
}: RouteErrorBoundaryGateProps) {
  const location = useLocation()
  return (
    <RouteErrorBoundary
      resetKey={location.key}
      route={location.pathname}
      track={track}
      mode={mode}
      snapshotId={snapshotId}
    >
      {children}
    </RouteErrorBoundary>
  )
}
