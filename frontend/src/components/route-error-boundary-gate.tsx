import type { ReactNode } from "react"
import { useLocation } from "react-router-dom"

import { RouteErrorBoundary } from "@/components/route-error-boundary"

export function RouteErrorBoundaryGate({ children }: { children: ReactNode }) {
  const location = useLocation()
  return <RouteErrorBoundary resetKey={location.key}>{children}</RouteErrorBoundary>
}
