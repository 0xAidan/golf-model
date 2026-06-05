import { useEffect, useRef, useState } from "react"

import { useInteraction } from "@/providers/interaction-provider"
import { NARROW_VIEWPORT_MAX_PX } from "@/hooks/use-media-query"
import { cn } from "@/lib/utils"

type CursorState = {
  x: number
  y: number
  visible: boolean
  label: string | null
  accent: "default" | "action" | "link"
}

const DEFAULT_STATE: CursorState = {
  x: 0,
  y: 0,
  visible: false,
  label: null,
  accent: "default",
}

function isFinePointerDevice(): boolean {
  if (typeof window === "undefined") return false
  return window.matchMedia("(pointer: fine)").matches && window.innerWidth > NARROW_VIEWPORT_MAX_PX
}

function readCursorTarget(target: EventTarget | null): {
  label: string | null
  accent: CursorState["accent"]
} | null {
  if (!(target instanceof Element)) return null
  const el = target.closest<HTMLElement>("[data-cursor]")
  if (!el) return null
  const accentRaw = el.dataset.cursorAccent
  const accent: CursorState["accent"] =
    accentRaw === "action" || accentRaw === "link" ? accentRaw : "default"
  return {
    label: el.dataset.cursorLabel ?? null,
    accent,
  }
}

export function MotionCursor() {
  const { reduceMotion } = useInteraction()
  const [enabled, setEnabled] = useState(false)
  const [state, setState] = useState<CursorState>(DEFAULT_STATE)
  const rafRef = useRef<number | null>(null)
  const pendingRef = useRef<Partial<CursorState>>({})

  useEffect(() => {
    setEnabled(isFinePointerDevice())
    const onResize = () => setEnabled(isFinePointerDevice())
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  useEffect(() => {
    if (!enabled || reduceMotion) return

    document.documentElement.classList.add("motion-cursor-active")

    const flush = () => {
      rafRef.current = null
      const patch = pendingRef.current
      pendingRef.current = {}
      if (Object.keys(patch).length === 0) return
      setState((prev) => ({ ...prev, ...patch }))
    }

    const schedule = (patch: Partial<CursorState>) => {
      pendingRef.current = { ...pendingRef.current, ...patch }
      if (rafRef.current == null) {
        rafRef.current = window.requestAnimationFrame(flush)
      }
    }

    const handleMove = (event: PointerEvent) => {
      const targetInfo = readCursorTarget(event.target)
      schedule({
        x: event.clientX,
        y: event.clientY,
        visible: true,
        label: targetInfo?.label ?? null,
        accent: targetInfo?.accent ?? "default",
      })
    }

    const handleLeave = () => {
      schedule({ visible: false, label: null, accent: "default" })
    }

    window.addEventListener("pointermove", handleMove, { passive: true })
    window.addEventListener("pointerleave", handleLeave)

    return () => {
      document.documentElement.classList.remove("motion-cursor-active")
      window.removeEventListener("pointermove", handleMove)
      window.removeEventListener("pointerleave", handleLeave)
      if (rafRef.current != null) {
        window.cancelAnimationFrame(rafRef.current)
      }
    }
  }, [enabled, reduceMotion])

  if (!enabled || reduceMotion) return null

  return (
    <div
      className={cn(
        "motion-cursor",
        state.visible && "motion-cursor--visible",
        state.accent !== "default" && `motion-cursor--${state.accent}`,
      )}
      aria-hidden
      style={{
        transform: `translate3d(${state.x}px, ${state.y}px, 0)`,
      }}
      data-testid="motion-cursor"
    >
      <span className="motion-cursor__ring" />
      {state.label ? <span className="motion-cursor__label">{state.label}</span> : null}
    </div>
  )
}
