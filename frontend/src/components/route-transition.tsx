import { useLocation } from "react-router-dom"
import { motion, useReducedMotion } from "framer-motion"
import type { ReactNode } from "react"

export function RouteTransition({ children }: { children: ReactNode }) {
  const location = useLocation()
  const reduceMotion = useReducedMotion()

  if (reduceMotion) {
    return <div className="route-motion-panel">{children}</div>
  }

  return (
    <motion.div
      key={location.pathname}
      className="route-motion-panel"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.14, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  )
}
