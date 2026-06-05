import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type { LiveTournamentSnapshot } from "@/lib/types"

import { DEFAULT_COCKPIT_MIN_EDGE } from "./workspace-constants"

export function TopPicksPipelineHint({
  diagnostics,
  predictionTab,
  minEdge,
  selectedBooksLength,
  matchupSearchTrimmed,
}: {
  diagnostics?: LiveTournamentSnapshot["diagnostics"]
  predictionTab: PredictionTab
  minEdge: number
  selectedBooksLength: number
  matchupSearchTrimmed: string
}) {
  if (predictionTab === "past") return null
  const filterActive =
    selectedBooksLength > 0 ||
    matchupSearchTrimmed.length > 0 ||
    minEdge > DEFAULT_COCKPIT_MIN_EDGE
  const st = diagnostics?.state
  const sel = diagnostics?.selection_counts
  const reasons = diagnostics?.reason_codes
  const topReasons = Object.entries(reasons ?? {})
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4)
  return (
    <div className="workspace-pipeline-hint">
      <div className="workspace-pipeline-title">Matchup pipeline</div>
      <div>
        State: <code>{st ?? "—"}</code>
        {sel?.input_rows != null ? (
          <>
            {" "}
            · Raw rows: <strong>{sel.input_rows}</strong>
          </>
        ) : null}
        {sel?.all_qualifying_rows != null ? (
          <>
            {" "}
            · Qualifying: <strong>{sel.all_qualifying_rows}</strong>
          </>
        ) : null}
        {sel?.selected_rows != null ? (
          <>
            {" "}
            · Card-selected: <strong>{sel.selected_rows}</strong>
          </>
        ) : null}
      </div>
      {topReasons.length > 0 ? (
        <div className="workspace-pipeline-exclusions">
          Top exclusions:{" "}
          {topReasons.map(([k, v], i) => (
            <span key={k}>
              {i > 0 ? " · " : null}
              <span title={k}>{k.replaceAll("_", " ")}</span> ({v})
            </span>
          ))}
        </div>
      ) : null}
      <div className="text-faint-11" style={{ marginTop: 6 }}>
        Top picks uses the same filters as the matchup board (books, search, min edge {(minEdge * 100).toFixed(0)}%; default{" "}
        {(DEFAULT_COCKPIT_MIN_EDGE * 100).toFixed(0)}%). Secondary markets can still show edges when matchups do not.
        {filterActive ? " Filters are active — relax them to see more qualifying rows." : null}
      </div>
    </div>
  )
}
