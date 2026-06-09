import { PentagonRadar } from "@/components/charts-v2"
import { SparklineChart } from "@/components/charts"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import type { FieldPercentileMap } from "@/features/players/player-workspace-types"
import { PLAYER_PROFILE_STAT_TOOLTIPS, SG_TRAJECTORY_HELP } from "@/lib/metric-tooltips"
import { computeSgTrajectoryBounds } from "@/lib/metric-heat"
import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"
import { cn } from "@/lib/utils"

const signed = (v?: number | null, d = 2) => {
  if (v == null) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(d)}`
}

const toneClass = (v?: number | null) => {
  if (v == null) return ""
  return v > 0 ? "metric--positive" : v < 0 ? "metric--negative" : ""
}

export const OverviewBentoGrid = ({
  standalone,
  modelPlayer,
  players,
  fieldPercentiles,
}: {
  standalone?: StandalonePlayerProfile
  modelPlayer?: CompositePlayer
  players: CompositePlayer[]
  fieldPercentiles: FieldPercentileMap
}) => {
  if (!standalone) return null

  const trajectoryBounds = computeSgTrajectoryBounds(players)
  const trendValues = standalone.trend_series?.filter((v) => Number.isFinite(v)) ?? []

  return (
    <div className="players-bento" data-testid="players-bento-grid">
      <div className="players-bento__tile players-bento__tile--model">
        <h3 className="players-bento__title">Model this week</h3>
        {modelPlayer ? (
          <div className="players-bento__model-grid">
            <div className="players-bento__metric">
              <span className="players-bento__metric-label">Model rank</span>
              <span className="players-bento__metric-value num">#{modelPlayer.rank}</span>
            </div>
            <div className="players-bento__metric">
              <span className="players-bento__metric-label">Composite</span>
              <span className="players-bento__metric-value num metric--positive">
                {modelPlayer.composite.toFixed(1)}
              </span>
              {fieldPercentiles.composite != null ? (
                <span className="players-bento__pct">{fieldPercentiles.composite}th pct</span>
              ) : null}
            </div>
            <div className="players-bento__metric">
              <span className="players-bento__metric-label">Form</span>
              <span className="players-bento__metric-value num">{modelPlayer.form.toFixed(1)}</span>
              {fieldPercentiles.form != null ? (
                <span className="players-bento__pct">{fieldPercentiles.form}th pct</span>
              ) : null}
            </div>
            <div className="players-bento__metric">
              <span className="players-bento__metric-label">Course fit</span>
              <span className="players-bento__metric-value num">{modelPlayer.course_fit.toFixed(1)}</span>
            </div>
            <div className="players-bento__metric players-bento__metric--wide" title={SG_TRAJECTORY_HELP}>
              <span className="players-bento__metric-label">SG trajectory</span>
              <SgTrajectoryMeter
                momentumTrend={modelPlayer.momentum_trend}
                momentumDirection={modelPlayer.momentum_direction}
                normMin={trajectoryBounds.min}
                normMax={trajectoryBounds.max}
              />
            </div>
          </div>
        ) : (
          <p className="players-bento__empty">Not in current field — model metrics unavailable.</p>
        )}
      </div>

      <div className="players-bento__tile players-bento__tile--radar">
        <h3 className="players-bento__title">Skill shape</h3>
        <PentagonRadar skills={standalone.sg_skills} playerName={standalone.player_display} height={280} />
      </div>

      <div className="players-bento__tile players-bento__tile--form">
        <h3 className="players-bento__title">Form momentum</h3>
        {trendValues.length > 0 ? (
          <SparklineChart values={trendValues} height={72} />
        ) : (
          <p className="players-bento__empty">No trend series</p>
        )}
        <div className="players-bento__windows">
          {(["10", "25", "50"] as const).map((w) => {
            const val = standalone.rolling_windows?.[w]
            return (
              <div key={w} className="players-bento__window" title={PLAYER_PROFILE_STAT_TOOLTIPS["Rolling windows"]}>
                <span className="players-bento__window-label">L{w}</span>
                <span className={cn("players-bento__window-value num", toneClass(val))}>
                  {signed(val, 3)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
