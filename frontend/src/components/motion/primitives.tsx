/**
 * Motion primitives for the terminal overhaul.
 * Every component degrades gracefully:
 *  - Calm Mode (CalmModeContext) -> opacity-only, no transforms
 *  - prefers-reduced-motion     -> instant (framer's useReducedMotion)
 */
import { motion, useReducedMotion, type HTMLMotionProps } from "framer-motion"
import type { ReactNode } from "react"

import { useCalmMode } from "@/providers/calm-mode-provider"

const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1]

type RevealProps = {
  children: ReactNode
  delay?: number
  className?: string
} & Omit<HTMLMotionProps<"div">, "children">

/** Fade-and-rise on mount. The workhorse entrance. */
export function Reveal({ children, delay = 0, className, ...rest }: RevealProps) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()
  const transformless = reduced || calm

  return (
    <motion.div
      className={className}
      initial={transformless ? { opacity: 0 } : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        transformless
          ? { duration: 0.12 }
          : { duration: 0.4, ease: EASE_OUT, delay }
      }
      {...rest}
    >
      {children}
    </motion.div>
  )
}

type StaggerProps = {
  children: ReactNode
  staggerMs?: number
  className?: string
}

/** Container that reveals direct children in sequence. Pair with <StaggerItem>. */
export function Stagger({ children, staggerMs = 30, className }: StaggerProps) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()

  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: {
          transition: { staggerChildren: reduced || calm ? 0 : staggerMs / 1000 },
        },
      }}
    >
      {children}
    </motion.div>
  )
}

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()
  const transformless = reduced || calm

  return (
    <motion.div
      className={className}
      variants={{
        hidden: transformless ? { opacity: 0 } : { opacity: 0, y: 8 },
        show: transformless
          ? { opacity: 1, transition: { duration: 0.12 } }
          : { opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE_OUT } },
      }}
    >
      {children}
    </motion.div>
  )
}

type CountUpNumberProps = {
  value: number
  format?: (value: number) => string
  className?: string
  durationMs?: number
}

/**
 * Animated number roll for hero metrics (no extra dep — framer-motion
 * animate() under the hood). Respects calm/reduced by snapping instantly.
 */
export function CountUpNumber({
  value,
  format = (v) => String(Math.round(v * 100) / 100),
  className,
  durationMs = 700,
}: CountUpNumberProps) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()

  if (reduced || calm) {
    return <span className={className}>{format(value)}</span>
  }

  return (
    <motion.span
      className={className}
      key={value}
      initial={{ opacity: 0.4, filter: "blur(2px)" }}
      animate={{ opacity: 1, filter: "blur(0px)" }}
      transition={{ duration: durationMs / 1000, ease: EASE_OUT }}
    >
      {format(value)}
    </motion.span>
  )
}

/** Springy hover lift for interactive cards. */
export function HoverLift({ children, className }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()
  if (reduced || calm) return <div className={className}>{children}</div>

  return (
    <motion.div
      className={className}
      whileHover={{ y: -3, transition: { duration: 0.16, ease: EASE_OUT } }}
      whileTap={{ scale: 0.99 }}
    >
      {children}
    </motion.div>
  )
}

/** Cinematic page-enter wrapper for route content. */
export function PageEnter({ children, className }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion()
  const { calm } = useCalmMode()

  return (
    <motion.div
      className={className}
      initial={
        reduced || calm ? { opacity: 0 } : { opacity: 0, y: 14, scale: 0.995 }
      }
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={
        reduced || calm
          ? { duration: 0.12 }
          : { duration: 0.45, ease: EASE_OUT }
      }
    >
      {children}
    </motion.div>
  )
}
