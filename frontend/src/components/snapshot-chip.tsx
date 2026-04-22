import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import {
  computeAgeSeconds,
  formatAgeLabel,
  normalizeSourceLabel,
  resolveTone,
} from "@/lib/snapshot-chip"

export type SnapshotChipProps = {
  generatedAt?: string | null
  dataSource?: string | null
  now?: () => number
}

export function SnapshotChip({ generatedAt, dataSource, now }: SnapshotChipProps) {
  const [nowMs, setNowMs] = useState<number>(() => (now ? now() : Date.now()))

  useEffect(() => {
    if (now) return
    const id = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [now])

  const effectiveNow = now ? now() : nowMs
  const ageSeconds = computeAgeSeconds(generatedAt, effectiveNow)
  const tone = resolveTone(ageSeconds)
  const ageLabel = formatAgeLabel(ageSeconds)
  const sourceLabel = normalizeSourceLabel(dataSource)

  return (
    <span
      className={cn("snapshot-chip", `snapshot-chip-${tone}`)}
      data-testid="snapshot-chip"
      data-tone={tone}
      data-source={sourceLabel}
      title={generatedAt ? `Snapshot generated at ${generatedAt}` : "No snapshot loaded yet"}
    >
      <span className="snapshot-chip-dot" aria-hidden />
      <span className="snapshot-chip-age" data-testid="snapshot-chip-age">
        {ageLabel}
      </span>
      <span className="snapshot-chip-sep" aria-hidden>·</span>
      <span className="snapshot-chip-source" data-testid="snapshot-chip-source">
        {sourceLabel}
      </span>
    </span>
  )
}
