import {
  EV_BADGE_TOOLTIP,
  TIER_BADGE_TOOLTIP,
} from "@/lib/metric-tooltips"

export function EdgeBadge({ ev, evPct }: { ev: number; evPct?: string }) {
  const cls = ev >= 0.08 ? "high" : ev >= 0.04 ? "medium" : "low"
  return (
    <span className={`ev-badge ${cls} help-cursor`} title={EV_BADGE_TOOLTIP}>
      {evPct ?? `${(ev * 100).toFixed(1)}%`}
    </span>
  )
}

export function TierBadge({
  tier,
  tierRationale,
  evKind,
}: {
  tier?: string
  tierRationale?: string
  evKind?: string
}) {
  const t = tier ?? "LEAN"
  const bits = [evKind, tierRationale].filter(Boolean)
  const title = bits.length > 0 ? bits.join(" — ") : TIER_BADGE_TOOLTIP
  return (
    <span className={`tier-badge ${t} help-cursor`} title={title}>
      {t}
    </span>
  )
}
