import { buildInsightSummary } from "@/features/players/insight-summary"
import type { FieldPercentileMap, LinkedPicksBundle } from "@/features/players/player-workspace-types"
import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"

export const InsightSummary = ({
  modelPlayer,
  standalone,
  fieldPercentiles,
  linkedPicks,
}: {
  modelPlayer?: CompositePlayer
  standalone?: StandalonePlayerProfile
  fieldPercentiles: FieldPercentileMap
  linkedPicks: LinkedPicksBundle
}) => {
  const text = buildInsightSummary({ modelPlayer, standalone, fieldPercentiles, linkedPicks })

  return (
    <p className="players-insight-summary" data-testid="players-insight-summary">
      {text}
    </p>
  )
}
