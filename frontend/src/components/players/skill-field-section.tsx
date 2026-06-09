import { useMemo } from "react"

import { ApproachArcGauges, BeeswarmStrip, PentagonRadar } from "@/components/charts-v2"
import type { ApproachBucket, BeeswarmCategory } from "@/components/charts-v2"
import { ModelCommandSection } from "@/components/product"
import { RollingHeatmap } from "@/components/players/rolling-heatmap"
import { HeroDataGrid } from "@/components/monitoring"
import { buildModelFieldValues } from "@/features/players/field-percentiles"
import type { FieldPercentileMap } from "@/features/players/player-workspace-types"
import {
  buildRollingSgGridColumns,
  type RollingSgGridRow,
} from "@/lib/players-columns"
import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"

const buildApproachBuckets = (
  approachBuckets: StandalonePlayerProfile["approach_buckets"],
): ApproachBucket[] => {
  const bucketMap: Record<string, { fw?: number; rgh?: number }> = {}
  for (const b of approachBuckets) {
    const isFw = b.label.toLowerCase().includes("fw") || b.key.toLowerCase().includes("_fw")
    const range = b.label.replace(/ ?FW| ?Rgh| ?Rough/gi, "").trim()
    if (!bucketMap[range]) bucketMap[range] = {}
    if (isFw) bucketMap[range].fw = b.value
    else bucketMap[range].rgh = b.value
  }
  return Object.entries(bucketMap)
    .filter(([, v]) => v.fw != null || v.rgh != null)
    .map(([label, v]) => ({ label, fw_sg: v.fw ?? 0, rgh_sg: v.rgh ?? 0 }))
}

export const SkillFieldSection = ({
  standalone,
  modelPlayer,
  players,
  fieldPercentiles,
}: {
  standalone: StandalonePlayerProfile
  modelPlayer?: CompositePlayer
  players: CompositePlayer[]
  fieldPercentiles: FieldPercentileMap
}) => {
  const fieldModelValues = useMemo(() => buildModelFieldValues(players), [players])

  const modelBeeswarmCategories = useMemo((): BeeswarmCategory[] => {
    if (!modelPlayer || !players.length) return []
    return [
      {
        label: "Composite",
        shortLabel: "COMP",
        playerValue: modelPlayer.composite,
        fieldValues: fieldModelValues.composite,
      },
      {
        label: "Form",
        shortLabel: "FORM",
        playerValue: modelPlayer.form,
        fieldValues: fieldModelValues.form,
      },
      {
        label: "Course Fit",
        shortLabel: "FIT",
        playerValue: modelPlayer.course_fit,
        fieldValues: fieldModelValues.course_fit,
      },
      {
        label: "Trajectory",
        shortLabel: "TRJ",
        playerValue: modelPlayer.momentum_trend ?? 0,
        fieldValues: fieldModelValues.momentum_trend,
      },
    ]
  }, [fieldModelValues, modelPlayer, players.length])

  const sgBeeswarmCategories = useMemo((): BeeswarmCategory[] => {
    const skills = standalone.sg_skills
    return [
      { label: "Total SG", shortLabel: "TOTAL", playerValue: skills.sg_total },
      { label: "Approach", shortLabel: "APP", playerValue: skills.sg_app },
      { label: "Around Green", shortLabel: "ARG", playerValue: skills.sg_arg },
      { label: "Putting", shortLabel: "PUTT", playerValue: skills.sg_putt },
      { label: "Off the Tee", shortLabel: "OTT", playerValue: skills.sg_ott },
    ]
  }, [standalone.sg_skills])

  const rollingGridRows = useMemo((): RollingSgGridRow[] => {
    if (!standalone.rolling_windows_expanded) return []
    return (["10", "25", "50"] as const).map((windowKey) => ({
      window: windowKey,
      sg_total: standalone.rolling_windows_expanded?.sg_total?.[windowKey],
      sg_ott: standalone.rolling_windows_expanded?.sg_ott?.[windowKey],
      sg_app: standalone.rolling_windows_expanded?.sg_app?.[windowKey],
      sg_arg: standalone.rolling_windows_expanded?.sg_arg?.[windowKey],
      sg_putt: standalone.rolling_windows_expanded?.sg_putt?.[windowKey],
      sg_t2g: standalone.rolling_windows_expanded?.sg_t2g?.[windowKey],
    }))
  }, [standalone.rolling_windows_expanded])

  const rollingColumns = useMemo(() => buildRollingSgGridColumns(), [])
  const approachArcBuckets = useMemo(
    () => buildApproachBuckets(standalone.approach_buckets),
    [standalone.approach_buckets],
  )

  return (
    <>
      <ModelCommandSection
        id="players-skills"
        title="Skills deep-dive"
        description="Radar profile, driving stats, and rolling SG heatmap"
        testId="players-section-skills"
      >
        <div className="players-skills-layout">
          <div className="players-skills-layout__radar">
            <PentagonRadar
              skills={standalone.sg_skills}
              playerName={standalone.player_display}
              height={340}
            />
          </div>
          <div className="players-skills-layout__side">
            <div className="players-skills-metric">
              <span className="players-skills-metric__label">Distance</span>
              <span className="players-skills-metric__value num">
                {standalone.sg_skills.driving_dist
                  ? `${standalone.sg_skills.driving_dist.toFixed(0)} yd`
                  : "—"}
              </span>
            </div>
            <div className="players-skills-metric">
              <span className="players-skills-metric__label">Accuracy</span>
              <span className="players-skills-metric__value num">
                {standalone.sg_skills.driving_acc
                  ? `${(standalone.sg_skills.driving_acc * 100).toFixed(1)}%`
                  : "—"}
              </span>
            </div>
            <RollingHeatmap data={standalone.rolling_windows_expanded} />
          </div>
        </div>
        {approachArcBuckets.length > 0 ? (
          <div className="players-approach-gauges">
            <h4 className="players-section-subtitle">Approach by distance</h4>
            <ApproachArcGauges buckets={approachArcBuckets} />
          </div>
        ) : null}
      </ModelCommandSection>

      {modelBeeswarmCategories.length > 0 ? (
        <ModelCommandSection
          id="players-field-model"
          title="Model vs field"
          description="Real field distribution from current composite board"
          testId="players-section-field-model"
        >
          <BeeswarmStrip categories={modelBeeswarmCategories} height={260} />
          <div className="players-percentile-badges">
            {fieldPercentiles.composite != null ? (
              <span className="players-percentile-badge">Composite {fieldPercentiles.composite}th</span>
            ) : null}
            {fieldPercentiles.form != null ? (
              <span className="players-percentile-badge">Form {fieldPercentiles.form}th</span>
            ) : null}
            {fieldPercentiles.course_fit != null ? (
              <span className="players-percentile-badge">Course fit {fieldPercentiles.course_fit}th</span>
            ) : null}
          </div>
        </ModelCommandSection>
      ) : null}

      <ModelCommandSection
        id="players-field-sg"
        title="Skill vs tour"
        description="Player SG categories (tour distribution reference)"
        testId="players-section-field-sg"
      >
        <BeeswarmStrip categories={sgBeeswarmCategories} height={280} />
      </ModelCommandSection>

      {rollingGridRows.length > 0 ? (
        <ModelCommandSection
          id="players-rolling-grid"
          title="Rolling windows grid"
          description="L10 / L25 / L50 by SG category"
          testId="players-section-rolling-grid"
        >
          <HeroDataGrid
            data={rollingGridRows}
            columns={rollingColumns}
            density="compact"
            getRowId={(row) => row.window}
            testId="players-profile-rolling-windows-grid"
          />
        </ModelCommandSection>
      ) : null}
    </>
  )
}
