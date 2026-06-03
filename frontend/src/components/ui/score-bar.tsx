import { formatNumber } from "@/lib/format"
import { heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"

export function ScoreBar({
  value,
  max = 100,
  color = "green",
}: {
  value: number
  max?: number
  color?: "green" | "gold" | "composite"
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const heatFill =
    (color === "green" || color === "composite") && max > 0 && Number.isFinite(value)
      ? heatSpectrumGradientAlongUnit(Math.min(1, Math.max(0, value / max)), "ltr")
      : undefined
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-track">
        <div
          className={heatFill ? "score-bar-fill" : `score-bar-fill ${color}`}
          style={heatFill ? { width: `${pct}%`, background: heatFill } : { width: `${pct}%` }}
        />
      </div>
      <span className="score-bar-val">{formatNumber(value, 1)}</span>
    </div>
  )
}
