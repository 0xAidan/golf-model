import { heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"
import { cn } from "@/lib/utils"

type Tone = "positive" | "negative" | "neutral"

export function PlayersKpiCell({
  label,
  value,
  tone: t = "neutral",
  sub,
  large = false,
  accentUnit,
  title,
}: {
  label: string
  value: string | React.ReactNode
  tone?: Tone
  sub?: string
  large?: boolean
  accentUnit?: number
  title?: string
}) {
  const onHeat = accentUnit != null
  return (
    <div
      title={title}
      className={cn("players-kpi-cell", title && "players-kpi-cell--help")}
      style={onHeat ? { background: heatSpectrumGradientAlongUnit(accentUnit, "ltr") } : undefined}
    >
      <span className={cn("players-kpi-label", onHeat && "players-kpi-label--on-heat")}>{label}</span>
      <span
        className={cn(
          "players-kpi-value",
          large && "players-kpi-value--lg",
          !onHeat && `players-kpi-value--${t}`,
          onHeat && "players-kpi-value--on-heat",
        )}
      >
        {value}
      </span>
      {sub ? (
        <span className={cn("players-kpi-sub", onHeat && "players-kpi-label--on-heat")}>{sub}</span>
      ) : null}
    </div>
  )
}
