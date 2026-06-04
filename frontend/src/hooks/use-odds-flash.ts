import { useEffect, useRef, useState } from "react"

export type OddsFlashDirection = "up" | "down"

export function useOddsFlashMap<T>(
  data: T[],
  getRowKey: (row: T) => string,
  getOddsValue: (row: T) => number | string | null | undefined,
): Record<string, OddsFlashDirection> {
  const prevRef = useRef<Map<string, number | string | null | undefined>>(new Map())
  const [flashMap, setFlashMap] = useState<Record<string, OddsFlashDirection>>({})

  useEffect(() => {
    const nextFlash: Record<string, OddsFlashDirection> = {}
    const nextPrev = new Map<string, number | string | null | undefined>()

    for (const row of data) {
      const key = getRowKey(row)
      const odds = getOddsValue(row)
      nextPrev.set(key, odds)
      const prior = prevRef.current.get(key)
      if (prior == null || odds == null) continue
      const priorNum = Number(prior)
      const oddsNum = Number(odds)
      if (!Number.isFinite(priorNum) || !Number.isFinite(oddsNum) || priorNum === oddsNum) continue
      nextFlash[key] = oddsNum > priorNum ? "up" : "down"
    }

    prevRef.current = nextPrev

    if (Object.keys(nextFlash).length === 0) return

    setFlashMap(nextFlash)
    const timer = window.setTimeout(() => setFlashMap({}), 320)
    return () => window.clearTimeout(timer)
  }, [data, getRowKey, getOddsValue])

  return flashMap
}
