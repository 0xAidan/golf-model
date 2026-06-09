import { ChevronRight } from "lucide-react"

import { EmptyState } from "@/components/ui/empty-state"
import type { LinkedPicksBundle } from "@/features/players/player-workspace-types"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

export const LinkedPicksPanel = ({
  playerKey,
  playerDisplay,
  linkedPicks,
}: {
  playerKey: string
  playerDisplay: string
  linkedPicks: LinkedPicksBundle
}) => {
  if (linkedPicks.totalCount === 0) {
    return (
      <div data-testid="players-linked-picks-empty">
        <EmptyState
          message="No +EV picks for this player"
          description="When the model finds edges involving this player, they will appear here and on the Dashboard."
          className="players-linked-picks-empty"
        />
      </div>
    )
  }

  return (
    <div className="players-linked-picks" data-testid="players-linked-picks">
      {linkedPicks.matchups.map((m) => {
        const isPick = m.pick_key === playerKey
        const role = isPick ? "Pick" : "Opponent"
        const otherName = isPick ? m.opponent : m.pick
        return (
          <a
            key={`${m.pick_key}-${m.opponent_key}-${m.book}-${m.odds}`}
            href="/?tab=full-picks"
            className="players-pick-card"
            data-testid="players-pick-card-matchup"
          >
            <div className="players-pick-card__header">
              <span className="players-pick-card__type">Matchup · {role}</span>
              <span className="players-pick-card__ev num metric--positive">{m.ev_pct}</span>
            </div>
            <div className="players-pick-card__body">
              <strong>{playerDisplay}</strong>
              <span className="players-pick-card__vs">vs</span>
              <span>{otherName}</span>
            </div>
            <div className="players-pick-card__meta">
              <span>{m.book ?? "—"} · {m.odds}</span>
              {m.tier ? <span className="players-pick-card__tier">{m.tier}</span> : null}
            </div>
            {m.reason ? (
              <p className="players-pick-card__reason">{m.reason}</p>
            ) : null}
            <span className="players-pick-card__link">
              View on Dashboard <ChevronRight size={14} aria-hidden />
            </span>
          </a>
        )
      })}

      {linkedPicks.secondary.map((bet, idx) => (
        <a
          key={`${bet.player_key}-${bet.market}-${idx}`}
          href="/?tab=full-picks"
          className="players-pick-card"
          data-testid="players-pick-card-secondary"
        >
          <div className="players-pick-card__header">
            <span className="players-pick-card__type">{bet.market}</span>
            <span className={cn("players-pick-card__ev num", bet.ev > 0 && "metric--positive")}>
              {formatNumber(bet.ev * 100, 1)}%
            </span>
          </div>
          <div className="players-pick-card__body">
            <strong>{bet.player_display ?? bet.player}</strong>
          </div>
          <div className="players-pick-card__meta">
            <span>{bet.book ?? "—"} · {bet.odds}</span>
            {bet.confidence ? <span className="players-pick-card__tier">{bet.confidence}</span> : null}
          </div>
          <span className="players-pick-card__link">
            View on Dashboard <ChevronRight size={14} aria-hidden />
          </span>
        </a>
      ))}
    </div>
  )
}
