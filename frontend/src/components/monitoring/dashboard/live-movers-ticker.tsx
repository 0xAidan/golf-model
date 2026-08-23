import { TickerItem } from "./phase-elements"
import type { LiveLeaderboardRow } from "@/lib/types"

/**
 * LiveMoversTicker — horizontal scrolling strip of the biggest
 * leaderboard movers since the pre-tee baseline. Renders nothing
 * without movement data. CSS-driven (overhaul.css .ticker), pauses
 * on hover, disabled under calm/reduced-motion.
 */
export function LiveMoversTicker({ rows }: { rows: LiveLeaderboardRow[] }) {
  const movers = rows
    .filter((row) => typeof row.leaderboard_delta === "number" && row.leaderboard_delta !== 0)
    .sort((a, b) => Math.abs(b.leaderboard_delta ?? 0) - Math.abs(a.leaderboard_delta ?? 0))
    .slice(0, 10)

  if (movers.length === 0) return null

  // Duplicate the track so translateX(-50%) loops seamlessly.
  const doubled = [...movers, ...movers]

  return (
    <div className="ticker panel--flat glass-bar" data-testid="live-movers-ticker" aria-label="Biggest leaderboard movers">
      <div className="ticker-track py-2">
        {doubled.map((row, index) => (
          <TickerItem
            key={`${row.player_key ?? row.player}-${index}`}
            name={row.player}
            delta={-(row.leaderboard_delta ?? 0)}
            detail={row.total_to_par != null ? `${row.total_to_par > 0 ? "+" : ""}${row.total_to_par}` : undefined}
          />
        ))}
      </div>
    </div>
  )
}
