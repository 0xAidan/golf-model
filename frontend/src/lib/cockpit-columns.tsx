import type { ColumnDef } from "@tanstack/react-table"
import { ChevronDown } from "lucide-react"
import type { ReactNode } from "react"

import { EdgeBadge, TierBadge } from "@/components/ui/edge-badge"
import { ScoreBar } from "@/components/ui/score-bar"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import { formatNumber, formatUnits } from "@/lib/format"
import {
  GRADING_TABLE_TOOLTIPS,
  MATCHUP_DETAIL_TOOLTIPS,
  MATCHUP_TABLE_TOOLTIPS,
  POWER_RANKINGS_HELP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"
import type { CompositePlayer, FlattenedSecondaryBet, MatchupBet } from "@/lib/types"
import { cn } from "@/lib/utils"
import { buildMatchupKey, secondaryBadgeLabel } from "@/pages/page-shared"

export type RankingsColumnOptions = {
  onPlayerSelect: (playerKey: string) => void
  trajectoryBounds: { min: number; max: number }
}

export function buildRankingsColumns({
  onPlayerSelect,
  trajectoryBounds,
}: RankingsColumnOptions): ColumnDef<CompositePlayer, unknown>[] {
  return [
    {
      id: "rank",
      accessorKey: "rank",
      header: "#",
      meta: { label: "Rank", align: "left", sticky: true, mono: true },
      enableSorting: true,
    },
    {
      id: "player",
      accessorKey: "player_display",
      header: "Player",
      meta: { label: "Player", sticky: true },
      enableSorting: true,
      cell: ({ row }) => (
        <button
          type="button"
          className="player-name-btn"
          onClick={(e) => {
            e.stopPropagation()
            onPlayerSelect(row.original.player_key)
          }}
        >
          {row.original.player_display}
        </button>
      ),
    },
    {
      id: "composite",
      accessorKey: "composite",
      header: "Composite",
      meta: { label: "Composite", align: "right" },
      enableSorting: true,
      cell: ({ row }) => <ScoreBar value={row.original.composite} max={100} color="composite" />,
    },
    {
      id: "form",
      accessorKey: "form",
      header: "Form",
      meta: { label: "Form", align: "right" },
      enableSorting: true,
      cell: ({ row }) => <ScoreBar value={row.original.form} max={100} color="green" />,
    },
    {
      id: "course",
      accessorKey: "course_fit",
      header: "Course",
      meta: { label: "Course", align: "right" },
      enableSorting: true,
      cell: ({ row }) => <ScoreBar value={row.original.course_fit} max={100} color="gold" />,
    },
    {
      id: "sgTrajectory",
      header: "SG traj",
      meta: { label: "SG trajectory", align: "center" },
      cell: ({ row }) => (
        <SgTrajectoryMeter
          momentumTrend={row.original.momentum_trend}
          momentumDirection={row.original.momentum_direction}
          normMin={trajectoryBounds.min}
          normMax={trajectoryBounds.max}
        />
      ),
    },
  ]
}

export type PickColumnOptions = {
  isPast: boolean
  renderResult?: (matchup: MatchupBet) => ReactNode
  renderExpandDetail?: (matchup: MatchupBet) => ReactNode
}

export function buildPickColumns({
  isPast,
  renderResult,
}: PickColumnOptions): ColumnDef<MatchupBet, unknown>[] {
  const cols: ColumnDef<MatchupBet, unknown>[] = [
    {
      id: "pick",
      header: "Pick",
      meta: { label: "Pick", sticky: true },
      cell: ({ row }) => {
        const m = row.original
        return (
          <div>
            <div className="pick-primary">{m.pick}</div>
            <div className="text-muted-11">vs {m.opponent}</div>
          </div>
        )
      },
    },
    {
      id: "bookOdds",
      header: "Book · Odds",
      meta: { label: "Book · Odds" },
      cell: ({ row }) => {
        const m = row.original
        return (
          <div>
            <div className="text-muted-11">{m.book ?? "—"}</div>
            <div className="pick-odds">{m.odds}</div>
          </div>
        )
      },
    },
    {
      id: "tier",
      header: "Tier",
      meta: { label: "Tier", align: "center" },
      cell: ({ row }) => (
        <TierBadge
          tier={row.original.tier}
          tierRationale={row.original.tier_rationale}
          evKind={row.original.ev_kind}
        />
      ),
    },
  ]

  if (isPast && renderResult) {
    cols.push({
      id: "result",
      header: "Res.",
      meta: { label: "Result", align: "center" },
      cell: ({ row }) => renderResult(row.original),
    })
  }

  cols.push(
    {
      id: "ev",
      accessorKey: "ev",
      header: "EV",
      meta: { label: "EV", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => <EdgeBadge ev={row.original.ev} evPct={row.original.ev_pct} />,
    },
    {
      id: "winPct",
      header: "Win%",
      meta: { label: "Win%", align: "right", mono: true },
      cell: ({ row }) => (
        <span className="num text-muted-11 help-cursor" title={MATCHUP_TABLE_TOOLTIPS.winPct}>
          {(row.original.model_win_prob * 100).toFixed(1)}%
        </span>
      ),
    },
    {
      id: "expand",
      header: "",
      meta: { label: "Expand" },
      cell: () => <ChevronDown size={14} className="expand-chevron" aria-hidden />,
    },
  )

  return cols
}

export type SecondaryColumnOptions = {
  isPast: boolean
  onPlayerSelect: (playerKey: string) => void
  renderResult?: (bet: FlattenedSecondaryBet) => ReactNode
}

export function buildSecondaryColumns({
  isPast,
  onPlayerSelect,
  renderResult,
}: SecondaryColumnOptions): ColumnDef<FlattenedSecondaryBet, unknown>[] {
  const cols: ColumnDef<FlattenedSecondaryBet, unknown>[] = [
    {
      id: "player",
      header: "Player",
      meta: { label: "Player", sticky: true },
      cell: ({ row }) => (
        <button
          type="button"
          className="player-name-btn"
          onClick={(e) => {
            e.stopPropagation()
            if (row.original.player_key) onPlayerSelect(row.original.player_key)
          }}
        >
          {row.original.player}
        </button>
      ),
    },
    {
      id: "market",
      header: "Market",
      meta: { label: "Market" },
      cell: ({ row }) => {
        const tier = (row.original.confidence ?? "LEAN").toUpperCase()
        return (
          <div className="flex-wrap-gap-6">
            <span className={`tier-badge ${tier} tier-badge--xs`}>{tier}</span>
            <span className="text-muted-11">{secondaryBadgeLabel(row.original.market)}</span>
          </div>
        )
      },
    },
  ]

  if (isPast && renderResult) {
    cols.push({
      id: "result",
      header: "Res.",
      meta: { label: "Result", align: "center" },
      cell: ({ row }) => renderResult(row.original),
    })
  }

  cols.push(
    {
      id: "bookOdds",
      header: "Book · Odds",
      meta: { label: "Book · Odds" },
      cell: ({ row }) => (
        <span className="text-muted-11">
          {row.original.book
            ? `${row.original.book} · ${row.original.odds}`
            : row.original.odds}
        </span>
      ),
    },
    {
      id: "ev",
      accessorKey: "ev",
      header: "EV",
      meta: { label: "EV", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => <EdgeBadge ev={row.original.ev} />,
    },
  )

  return cols
}

export type RecentResultRow = {
  kind: "graded" | "replay"
  event: { event_id?: string; name: string; total_profit?: number | null; graded_pick_count?: number; hits?: number }
}

export function buildRecentResultsColumns(): ColumnDef<RecentResultRow, unknown>[] {
  return [
    {
      id: "event",
      header: "Event",
      meta: { label: "Event", sticky: true },
      cell: ({ row }) => (
        <span className="player-name">
          {row.original.event.name}
          {row.original.kind === "replay" ? <span className="replay-tag">replay</span> : null}
        </span>
      ),
    },
    {
      id: "pl",
      header: "P&L",
      meta: { label: "P&L", align: "right", mono: true },
      cell: ({ row }) => {
        const profit =
          row.original.event.total_profit == null
            ? null
            : Number(row.original.event.total_profit ?? 0)
        return (
          <span
            className={`num ${
              profit == null
                ? "profit-muted"
                : profit >= 0
                  ? "profit-positive"
                  : "profit-negative"
            }`}
          >
            {profit == null ? "—" : formatUnits(profit)}
          </span>
        )
      },
    },
    {
      id: "hitPct",
      header: "Hit%",
      meta: { label: "Hit%", align: "right", mono: true },
      cell: ({ row }) => {
        const picks = row.original.event.graded_pick_count ?? 0
        const hits = row.original.event.hits ?? 0
        const hr = picks > 0 ? `${((hits / picks) * 100).toFixed(0)}%` : "—"
        return <span className="num text-muted-11">{hr}</span>
      },
    },
  ]
}

export function buildPicksPageMatchupColumns(): ColumnDef<MatchupBet, unknown>[] {
  return [
    {
      id: "pickVsOpp",
      header: "Pick vs Opponent",
      meta: { label: "Pick vs Opponent", sticky: true },
      cell: ({ row }) => {
        const m = row.original
        return (
          <div>
            <div className="pick-primary">{m.pick}</div>
            <div className="text-muted-11">vs {m.opponent}</div>
          </div>
        )
      },
    },
    {
      id: "book",
      accessorKey: "book",
      header: "Book",
      meta: { label: "Book" },
      cell: ({ row }) => <span className="text-muted-11">{row.original.book ?? "—"}</span>,
    },
    {
      id: "odds",
      accessorKey: "odds",
      header: "Odds",
      meta: { label: "Odds", mono: true },
      cell: ({ row }) => <span className="pick-odds">{row.original.odds}</span>,
    },
    {
      id: "tier",
      header: "Tier",
      meta: { label: "Tier", align: "center" },
      cell: ({ row }) => (
        <TierBadge
          tier={row.original.tier}
          tierRationale={row.original.tier_rationale}
          evKind={row.original.ev_kind}
        />
      ),
    },
    {
      id: "ev",
      accessorKey: "ev",
      header: "EV",
      meta: { label: "EV", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => <EdgeBadge ev={row.original.ev} evPct={row.original.ev_pct} />,
    },
    {
      id: "winPct",
      header: "Win%",
      meta: { label: "Win%", align: "right", mono: true },
      cell: ({ row }) => (
        <span className="num text-muted-11 help-cursor" title={MATCHUP_TABLE_TOOLTIPS.winPct}>
          {(row.original.model_win_prob * 100).toFixed(1)}%
        </span>
      ),
    },
    {
      id: "expand",
      header: "",
      cell: () => <ChevronDown size={14} className="expand-chevron" aria-hidden />,
    },
  ]
}

export type LeaderboardColumnOptions = {
  onPlayerSelect: (playerKey: string) => void
}

export function buildLeaderboardColumns({
  onPlayerSelect,
}: LeaderboardColumnOptions): ColumnDef<import("@/lib/cockpit-event-models").CockpitLeaderboardRowModel, unknown>[] {
  return [
    {
      id: "pos",
      accessorKey: "positionLabel",
      header: "Pos",
      meta: { label: "Pos", mono: true },
    },
    {
      id: "player",
      header: "Player",
      meta: { label: "Player", sticky: true },
      cell: ({ row }) => {
        const r = row.original
        return (
          <div>
            {r.playerKey ? (
              <button
                type="button"
                className="player-name-btn"
                onClick={(e) => {
                  e.stopPropagation()
                  onPlayerSelect(r.playerKey!)
                }}
              >
                {r.playerLabel}
              </button>
            ) : (
              r.playerLabel
            )}
            {r.detail ? <div className="leaderboard-row-detail">{r.detail}</div> : null}
          </div>
        )
      },
    },
    {
      id: "score",
      accessorKey: "toParLabel",
      header: "Score",
      meta: { label: "Score", align: "right", mono: true },
    },
    {
      id: "rd",
      accessorKey: "roundLabel",
      header: "Rd",
      meta: { label: "Rd", align: "right", mono: true },
    },
    {
      id: "tot",
      accessorKey: "scoreLabel",
      header: "Tot",
      meta: { label: "Tot", align: "right", mono: true },
    },
  ]
}

function failedReasonBadge(reasonCode: string) {
  const map: Record<string, { label: string; className: string }> = {
    below_ev_threshold: { label: "Below EV", className: "reason-badge reason-badge--muted" },
    dg_model_disagreement: { label: "DG disagree", className: "reason-badge reason-badge--gold" },
  }
  const entry = map[reasonCode] ?? { label: reasonCode, className: "reason-badge reason-badge--muted" }
  return <span className={entry.className}>{entry.label}</span>
}

export function buildFailedCandidateColumns(): ColumnDef<import("@/lib/types").FailedMatchupCandidate, unknown>[] {
  return [
    {
      id: "pickVsOpp",
      header: "Pick vs Opponent",
      meta: { label: "Pick vs Opponent", sticky: true },
      cell: ({ row }) => {
        const c = row.original
        return (
          <div>
            <div className="pick-primary">{c.pick}</div>
            <div className="text-muted-11">vs {c.opponent}</div>
          </div>
        )
      },
    },
    {
      id: "book",
      accessorKey: "book",
      header: "Book",
      meta: { label: "Book" },
      cell: ({ getValue }) => <span className="text-muted-11">{(getValue() as string | null) ?? "—"}</span>,
    },
    {
      id: "odds",
      accessorKey: "odds",
      header: "Odds",
      meta: { label: "Odds", mono: true },
      cell: ({ getValue }) => <span className="pick-odds">{getValue() != null ? String(getValue()) : "—"}</span>,
    },
    {
      id: "reason",
      accessorKey: "reason_code",
      header: "Reason",
      meta: { label: "Reason", align: "center" },
      cell: ({ getValue }) => failedReasonBadge(String(getValue() ?? "")),
    },
    {
      id: "ev",
      accessorKey: "ev",
      header: "EV",
      meta: { label: "EV", align: "right", mono: true },
      cell: ({ row }) => {
        const c = row.original
        const evDisplay =
          c.ev_pct ??
          (c.ev != null && c.ev !== undefined ? `${(c.ev * 100).toFixed(1)}%` : "—")
        return (
          <span className={cn("num help-cursor", c.ev != null && c.ev >= 0 ? "text-primary" : "text-muted-11")}>
            {evDisplay}
          </span>
        )
      },
    },
    {
      id: "winPct",
      header: "Win%",
      meta: { label: "Win%", align: "right", mono: true },
      cell: ({ row }) => {
        const c = row.original
        const winPct =
          c.model_win_prob != null ? `${(c.model_win_prob * 100).toFixed(1)}%` : "—"
        return <span className="num text-muted-11">{winPct}</span>
      },
    },
  ]
}

export {
  POWER_RANKINGS_HELP,
  MATCHUP_TABLE_TOOLTIPS,
  MATCHUP_DETAIL_TOOLTIPS,
  GRADING_TABLE_TOOLTIPS,
  SG_TRAJECTORY_HELP,
  buildMatchupKey,
}
