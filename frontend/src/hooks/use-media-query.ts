import { useSyncExternalStore } from "react"

/** Viewport width at or below this value uses the compact (mobile) shell and dashboard layout. */
export const NARROW_VIEWPORT_MAX_PX = 767

export function useMediaQuery(query: string): boolean {
  const subscribe = (callback: () => void) => {
    if (typeof window === "undefined") return () => {}
    const mq = window.matchMedia(query)
    mq.addEventListener("change", callback)
    return () => mq.removeEventListener("change", callback)
  }

  const getSnapshot = () =>
    typeof window !== "undefined" && window.matchMedia(query).matches

  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}

export function useIsNarrowViewport(): boolean {
  return useMediaQuery(`(max-width: ${NARROW_VIEWPORT_MAX_PX}px)`)
}
