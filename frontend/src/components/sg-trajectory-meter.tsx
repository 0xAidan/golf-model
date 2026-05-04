import { heatHslFromUnit, heatUnitForTrajectory, nominalTrajectoryFromDirection } from "@/lib/metric-heat"

const TRAJECTORY_HELP =
  "Rolling SG:TOT rank movement across time windows (vs career-long baseline). Not the same as last week’s tournament finish."

export function SgTrajectoryMeter({
  momentumTrend,
  momentumDirection,
  normMin,
  normMax,
}: {
  momentumTrend?: number
  momentumDirection?: string
  normMin: number
  normMax: number
}) {
  const raw =
    momentumTrend ??
    nominalTrajectoryFromDirection(momentumDirection) ??
    0
  const heatT = heatUnitForTrajectory(raw, normMin, normMax)
  const color = heatHslFromUnit(heatT)
  const mid = (normMin + normMax) / 2
  const half = Math.max(mid - normMin, normMax - mid, 1e-6)
  const n = Math.min(1, Math.max(-1, (raw - mid) / half))
  const fillPct = Math.abs(n) * 50

  const label = `${raw > 0 ? "+" : ""}${raw.toFixed(1)}`

  return (
    <div
      className="sg-traj-meter"
      title={TRAJECTORY_HELP}
      style={{ ["--sg-traj-fill" as string]: color }}
    >
      <div className="sg-traj-track" aria-hidden>
        <div className="sg-traj-mid" />
        {n >= 0 ? (
          <div className="sg-traj-fill sg-traj-fill-right" style={{ width: `${fillPct}%` }} />
        ) : (
          <div className="sg-traj-fill sg-traj-fill-left" style={{ width: `${fillPct}%` }} />
        )}
      </div>
      <span className="sg-traj-val" style={{ color }}>
        {label}
      </span>
    </div>
  )
}
