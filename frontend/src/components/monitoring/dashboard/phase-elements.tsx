import { Reveal } from "@/components/motion/primitives"
import { detectPhase } from "@/lib/tournament-phase"
import type { LiveRefreshSnapshot } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Phase identity chip — tells the operator what mode the terminal is in. */
export function PhaseChip({ snapshot, className }: { snapshot: LiveRefreshSnapshot | null | undefined; className?: string }) {
  const phase = detectPhase(snapshot)

  return (
    <Reveal className={className}>
      <span
        className="phase-chip"
        style={{ "--phase-accent": phase.accent } as React.CSSProperties}
        data-testid="phase-chip"
        data-phase={phase.phase}
        title={phase.blurb}
      >
        <span className="phase-chip__dot" aria-hidden />
        {phase.label}
      </span>
    </Reveal>
  )
}

/** Phase blurb line under the event title. */
export function PhaseBlurb({ snapshot }: { snapshot: LiveRefreshSnapshot | null | undefined }) {
  const phase = detectPhase(snapshot)
  return (
    <p className="text-xs text-[var(--text-muted)]" data-testid="phase-blurb">
      {phase.blurb}
    </p>
  )
}

/** One row of the movers ticker. */
export function TickerItem({
  name,
  delta,
  detail,
}: {
  name: string
  delta: number
  detail?: string
}) {
  const up = delta > 0
  return (
    <span className="ticker-item" data-testid="ticker-item">
      <span className="text-[var(--text)]">{name}</span>
      <span className={cn(up ? "ticker-item__delta--up" : "ticker-item__delta--down")}>
        {up ? "▲" : "▼"} {Math.abs(delta)}
      </span>
      {detail ? <span className="text-[var(--text-faint)]">{detail}</span> : null}
    </span>
  )
}
