import { useLocation } from "react-router-dom"
import { AnimatePresence, motion } from "framer-motion"
import type { ReactNode } from "react"

import { useInteraction } from "@/providers/interaction-provider"

export function RouteTransition({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { reduceMotion, viewTransitionsEnabled } = useInteraction()

  if (reduceMotion) {
    return <div className="route-motion-panel">{children}</div>
  }

  if (viewTransitionsEnabled) {
    return (
      <div
        key={location.pathname}
        className="route-motion-panel route-motion-panel--view-transition"
        style={{ viewTransitionName: "route-panel" }}
      >
        {children}
      </div>
    )
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        className="route-motion-panel"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
