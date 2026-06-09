import type { CompositePlayer } from "@/lib/types"
import type { StandalonePlayerProfile } from "@/lib/types"

import type { FieldPercentileMap, LinkedPicksBundle } from "./player-workspace-types"

const signed = (v: number, d = 1) => `${v > 0 ? "+" : ""}${v.toFixed(d)}`

const quartileLabel = (pct: number | null | undefined): string | null => {
  if (pct == null) return null
  if (pct >= 75) return "top quartile"
  if (pct >= 50) return "above median"
  if (pct >= 25) return "below median"
  return "bottom quartile"
}

export const buildInsightSummary = ({
  modelPlayer,
  standalone,
  fieldPercentiles,
  linkedPicks,
}: {
  modelPlayer?: CompositePlayer
  standalone?: StandalonePlayerProfile
  fieldPercentiles: FieldPercentileMap
  linkedPicks: LinkedPicksBundle
}): string => {
  const parts: string[] = []

  if (modelPlayer) {
    parts.push(`Model ranks #${modelPlayer.rank} in field`)
    const formQ = quartileLabel(fieldPercentiles.form)
    if (formQ) {
      parts.push(`form ${modelPlayer.form.toFixed(1)} (${formQ})`)
    }
  } else if (standalone?.header.dg_rank) {
    parts.push(`DG rank #${standalone.header.dg_rank}`)
  }

  const skills = standalone?.sg_skills
  if (skills) {
    const areas = [
      { label: "Approach", v: skills.sg_app },
      { label: "OTT", v: skills.sg_ott },
      { label: "Putting", v: skills.sg_putt },
      { label: "ARG", v: skills.sg_arg },
    ].filter((a) => a.v != null) as Array<{ label: string; v: number }>
    if (areas.length) {
      const best = [...areas].sort((a, b) => b.v - a.v)[0]
      parts.push(`strongest in ${best.label} (${signed(best.v)})`)
    }
  }

  if (linkedPicks.totalCount > 0) {
    parts.push(
      `${linkedPicks.totalCount} +EV pick${linkedPicks.totalCount === 1 ? "" : "s"} this week`,
    )
  }

  if (!parts.length) {
    return "Select a player to see model context, skills, and linked picks."
  }

  return parts.join("; ") + "."
}
