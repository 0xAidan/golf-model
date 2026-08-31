import type { ReactNode } from "react"

export function RouteTransition({ children }: { children: ReactNode }) {
  return <div className="route-motion-panel">{children}</div>
}
