import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react"
import { useReducedMotion } from "framer-motion"

type ViewTransitionDocument = Document & {
  startViewTransition?: (callback: () => void | Promise<void>) => { finished: Promise<void> }
}

export type InteractionContextValue = {
  reduceMotion: boolean
  viewTransitionsEnabled: boolean
  startViewTransition: (update: () => void | Promise<void>) => void
}

const InteractionContext = createContext<InteractionContextValue | null>(null)

function subscribeReducedMotion(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {}
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
  mq.addEventListener("change", onStoreChange)
  return () => mq.removeEventListener("change", onStoreChange)
}

function getReducedMotionSnapshot() {
  if (typeof window === "undefined") return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

export function InteractionProvider({ children }: { children: ReactNode }) {
  const framerReduceMotion = useReducedMotion()
  const systemReduceMotion = useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotionSnapshot,
    () => false,
  )

  const reduceMotion = Boolean(framerReduceMotion ?? systemReduceMotion)

  const viewTransitionsEnabled = useMemo(() => {
    if (reduceMotion || typeof document === "undefined") return false
    return typeof (document as ViewTransitionDocument).startViewTransition === "function"
  }, [reduceMotion])

  const startViewTransition = useCallback(
    (update: () => void | Promise<void>) => {
      if (!viewTransitionsEnabled) {
        void update()
        return
      }
      ;(document as ViewTransitionDocument).startViewTransition?.(() => update())
    },
    [viewTransitionsEnabled],
  )

  const value = useMemo<InteractionContextValue>(
    () => ({
      reduceMotion,
      viewTransitionsEnabled,
      startViewTransition,
    }),
    [reduceMotion, viewTransitionsEnabled, startViewTransition],
  )

  return <InteractionContext.Provider value={value}>{children}</InteractionContext.Provider>
}

export function useInteraction(): InteractionContextValue {
  const ctx = useContext(InteractionContext)
  if (!ctx) {
    throw new Error("useInteraction must be used within InteractionProvider")
  }
  return ctx
}
