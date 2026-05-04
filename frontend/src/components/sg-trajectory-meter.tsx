import {
  heatSpectrumFromUnit,
  heatSpectrumGradientAlongUnit,
  heatUnitForTrajectory,
  nominalTrajectoryFromDirection,
} from "@/lib/metric-heat"
import { SG_TRAJECTORY_HELP as TRAJECTORY_HELP } from "@/lib/metric-tooltips"

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
  const color = heatSpectrumFromUnit(heatT)
  const mid = (normMin + normMax) / 2
  const half = Math.max(mid - normMin, normMax - mid, 1e-6)
  const n = Math.min(1, Math.max(-1, (raw - mid) / half))
  const fillPct = Math.abs(n) * 50
  const fillGradient =
    n >= 0 ? heatSpectrumGradientAlongUnit(heatT, "ltr") : heatSpectrumGradientAlongUnit(heatT, "rtl")

  const label = `${raw > 0 ? "+" : ""}${raw.toFixed(1)}`

  return (
    <div
      className="sg-traj-meter"
      title={TRAJECTORY_HELP}
      role="img"
      aria-label={`Rolling strokes-gained trajectory ${label}. ${TRAJECTORY_HELP}`}
    >
      <div className="sg-traj-track" aria-hidden>
        <div className="sg-traj-mid" />
        {n >= 0 ? (
          <div
            className="sg-traj-fill sg-traj-fill-right"
            style={{ width: `${fillPct}%`, background: fillGradient }}
          />
        ) : (
          <div
            className="sg-traj-fill sg-traj-fill-left"
            style={{ width: `${fillPct}%`, background: fillGradient }}
          />
        )}
      </div>
      <span className="sg-traj-val" style={{ color }}>
        {label}
      </span>
    </div>
  )
}
