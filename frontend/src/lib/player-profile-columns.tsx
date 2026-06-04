import type { ColumnDef } from "@tanstack/react-table"

import { EdgeBadge } from "@/components/ui/edge-badge"
import { formatNumber } from "@/lib/format"
import { MATCHUP_TABLE_TOOLTIPS, PLAYER_PROFILE_TABLE_TOOLTIPS } from "@/lib/metric-tooltips"
import type { PlayerProfile } from "@/lib/types"
import { cn } from "@/lib/utils"

type RecentStart = NonNullable<
  NonNullable<PlayerProfile["course_event_context"]>["recent_starts"]
>[number]

type LinkedBet = PlayerProfile["linked_bets"][number]

function signed(v?: number | null, digits = 3): string {
  if (v == null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(digits)}`
}

function toneClass(v?: number | null): string {
  if (v == null) return "text-muted-11"
  return v > 0 ? "text-primary" : v < 0 ? "text-danger" : "text-muted-11"
}

export function buildProfileTournamentColumns(): ColumnDef<RecentStart, unknown>[] {
  return [
    {
      id: "event",
      accessorKey: "event_name",
      header: "Event",
      meta: { label: "Event", sticky: true },
      cell: ({ getValue }) => (
        <span className="player-name font-semibold">{String(getValue() ?? "—")}</span>
      ),
    },
    {
      id: "date",
      accessorKey: "event_completed",
      header: "Date",
      meta: { label: "Date" },
      cell: ({ getValue }) => (
        <span className="text-faint text-xs">{String(getValue() ?? "—")}</span>
      ),
    },
    {
      id: "finish",
      accessorKey: "fin_text",
      header: "Finish",
      meta: { label: "Finish", align: "center" },
      cell: ({ getValue }) => <span className="num text-muted-11">{String(getValue() ?? "—")}</span>,
    },
    {
      id: "avgSg",
      accessorKey: "avg_sg_total",
      header: "Avg SG",
      meta: { label: "Avg SG", align: "right", mono: true },
      cell: ({ row }) => (
        <span className={cn("num font-bold", toneClass(row.original.avg_sg_total))}>
          {signed(row.original.avg_sg_total)}
        </span>
      ),
    },
  ]
}

export function buildProfileBetsColumns(): ColumnDef<LinkedBet, unknown>[] {
  return [
    {
      id: "bet",
      header: "Bet",
      meta: { label: "Bet", sticky: true },
      cell: ({ row }) => {
        const bet = row.original
        return (
          <div>
            <div className="font-semibold">{bet.bet_type ?? "—"}</div>
            <div className="text-faint text-xs">
              {bet.player_display}
              {bet.opponent_display ? ` vs ${bet.opponent_display}` : ""}
            </div>
          </div>
        )
      },
    },
    {
      id: "odds",
      accessorKey: "market_odds",
      header: "Odds",
      meta: { label: "Odds" },
      cell: ({ getValue }) => (
        <span className="pick-odds font-mono font-semibold">{String(getValue() ?? "—")}</span>
      ),
    },
    {
      id: "ev",
      accessorKey: "ev",
      header: "EV",
      meta: { label: "EV", align: "right", mono: true },
      cell: ({ row }) => <EdgeBadge ev={row.original.ev ?? 0} />,
    },
    {
      id: "confidence",
      accessorKey: "confidence",
      header: "Confidence",
      meta: { label: "Confidence", align: "center" },
      cell: ({ getValue }) => {
        const tier = String(getValue() ?? "LEAN").toUpperCase()
        return <span className={`tier-badge ${tier}`}>{tier}</span>
      },
    },
  ]
}
