import { Link } from "react-router-dom"
import { Trophy } from "lucide-react"

import { formatUnits } from "@/lib/format"
import type { GradedTournamentSummary } from "@/lib/types"

export const ResultsPreview = ({
  latestEvent,
  pickSourceLabel = "Dashboard",
}: {
  latestEvent?: GradedTournamentSummary | null
  pickSourceLabel?: string
}) => {
  if (!latestEvent) {
    return (
      <div className="results-preview-card" data-testid="results-preview-empty">
        <div>
          <div className="text-sm font-semibold">No graded events yet</div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Grade an event from the header or open Results to review track record.
          </p>
        </div>
        <Link to="/results" className="btn btn-ghost btn-sm">
          Open Results
        </Link>
      </div>
    )
  }

  const profit = Number(latestEvent.total_profit ?? 0)

  return (
    <div className="results-preview-card" data-testid="results-preview">
      <div className="flex items-start gap-3">
        <Trophy size={18} className="mt-0.5 shrink-0 text-[var(--gold)]" aria-hidden />
        <div>
          <div className="text-sm font-semibold">Latest graded — {latestEvent.name}</div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {pickSourceLabel} · {latestEvent.graded_pick_count ?? 0} picks · P&amp;L{" "}
            <span className={profit >= 0 ? "metric--positive" : "metric--negative"}>
              {formatUnits(profit)}
            </span>
          </p>
        </div>
      </div>
      <Link to="/results" className="btn btn-ghost btn-sm">
        View all
      </Link>
    </div>
  )
}
