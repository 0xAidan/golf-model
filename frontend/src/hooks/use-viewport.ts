import { useSyncExternalStore } from "react"

/** Viewport tiers aligned with layout breakpoints in the mission spec. */
export type ViewportTier = "mobile" | "tablet" | "desktop"

const MOBILE_QUERY = "(max-width: 767px)"
const TABLET_QUERY = "(min-width: 768px) and (max-width: 1199px)"
const DESKTOP_QUERY = "(min-width: 1200px)"

function readTier(): ViewportTier {
  if (typeof window === "undefined") return "desktop"
  if (window.matchMedia(MOBILE_QUERY).matches) return "mobile"
  if (window.matchMedia(TABLET_QUERY).matches) return "tablet"
  if (window.matchMedia(DESKTOP_QUERY).matches) return "desktop"
  return "desktop"
}

function subscribe(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {}
  const media = [MOBILE_QUERY, TABLET_QUERY, DESKTOP_QUERY].map((q) => window.matchMedia(q))
  const handler = () => onStoreChange()
  for (const m of media) {
    m.addEventListener("change", handler)
  }
  return () => {
    for (const m of media) {
      m.removeEventListener("change", handler)
    }
  }
}

export function useViewportTier(): ViewportTier {
  return useSyncExternalStore(subscribe, readTier, () => "desktop")
}

export function useIsMobileViewport(): boolean {
  return useViewportTier() === "mobile"
}

export function useIsCompactViewport(): boolean {
  const tier = useViewportTier()
  return tier === "mobile" || tier === "tablet"
}
