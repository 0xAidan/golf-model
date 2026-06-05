import type { ColumnDef } from "@tanstack/react-table"
import { ChevronDown } from "lucide-react"
import type { ReactNode } from "react"

import { EdgeBadge, TierBadge } from "@/components/ui/edge-badge"
import { formatNumber, formatUnits } from "@/lib/format"
import {
  GRADING_TABLE_TOOLTIPS,
  MATCHUP_DETAIL_TOOLTIPS,
  MATCHUP_TABLE_TOOLTIPS,
  POWER_RANKINGS_HELP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import type { CompositePlayer, FlattenedSecondaryBet, MatchupBet } from "@/lib/types"
import { cn } from "@/lib/utils"
import { buildMatchupKey, secondaryBadgeLabel } from "@/pages/page-shared"

export type RankingsColumnOptions = {
  onPlayerSelect: (playerKey: string) => void
  trajectoryBounds: { min: number; max: number }
}

function buildPlayerColumn(onPlayerSelect: (playerKey: string) => void): ColumnDef<CompositePlayer, unknown> {
  return {
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
  }
}

/** Pre-tournament / upcoming / past replay — model-centric columns (restored behavior). */
export function buildUpcomingRankingsColumns({
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
      cell: ({ row }) => <span className="num">{formatRankCell(row.original.rank)}</span>,
    },
    buildPlayerColumn(onPlayerSelect),
    {
      id: "composite",
      accessorKey: "composite",
      header: "Composite",
      meta: { label: "Composite", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num help-cursor" title={POWER_RANKINGS_HELP.composite}>
          {formatNumber(row.original.composite, 1)}
        </span>
      ),
    },
    {
      id: "form",
      accessorKey: "form",
      header: "Form",
      meta: { label: "Form", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num help-cursor" title={POWER_RANKINGS_HELP.form}>
          {formatNumber(row.original.form, 1)}
        </span>
      ),
    },
    {
      id: "courseFit",
      accessorKey: "course_fit",
      header: "Course",
      meta: { label: "Course fit", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num help-cursor" title={POWER_RANKINGS_HELP.course}>
          {formatNumber(row.original.course_fit, 1)}
        </span>
      ),
    },
    {
      id: "momentum",
      accessorKey: "momentum",
      header: "Mom.",
      meta: { label: "Momentum", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num help-cursor" title={POWER_RANKINGS_HELP.momentum}>
          {formatNumber(row.original.momentum, 1)}
        </span>
      ),
    },
    {
      id: "sgTraj",
      header: "SG Traj",
      meta: { label: "SG trajectory", align: "center" },
      enableSorting: false,
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

/** Live tournament — dual model/scoring movement columns. */
export function buildLiveRankingsColumns({
  onPlayerSelect,
}: Omit<RankingsColumnOptions, "trajectoryBounds">): ColumnDef<CompositePlayer, unknown>[] {
  return [
    {
      id: "currentRank",
      accessorKey: "current_rank",
      header: "Model now",
      meta: { label: "Model now", align: "left", sticky: true, mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num">{formatRankCell(row.original.current_rank ?? row.original.rank)}</span>
      ),
    },
    buildPlayerColumn(onPlayerSelect),
    {
      id: "startModelRank",
      accessorKey: "start_rank",
      header: "Start (model)",
      meta: { label: "Start (model)", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num text-muted-11">{formatRankCell(row.original.start_rank)}</span>
      ),
    },
    {
      id: "modelDelta",
      accessorKey: "rank_delta",
      header: "Model Δ",
      meta: { label: "Model Δ", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span
          className="num"
          aria-label={formatModelDeltaAriaLabel(
            row.original.start_rank,
            row.original.current_rank ?? row.original.rank,
            row.original.rank_delta,
          )}
        >
          {formatMovementCell(row.original.rank_delta)}
        </span>
      ),
    },
    {
      id: "leaderboardPos",
      accessorKey: "leaderboard_position",
      header: "Pos",
      meta: { label: "Pos", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num">{row.original.leaderboard_position ?? "--"}</span>
      ),
    },
    {
      id: "leaderboardStartPos",
      accessorKey: "start_leaderboard_position",
      header: "Start pos",
      meta: { label: "Start pos", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num text-muted-11">{row.original.start_leaderboard_position ?? "--"}</span>
      ),
    },
    {
      id: "leaderboardDelta",
      accessorKey: "leaderboard_delta",
      header: "Pos Δ",
      meta: { label: "Pos Δ", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span
          className="num"
          aria-label={formatScoringDeltaAriaLabel(
            row.original.start_leaderboard_position,
            row.original.leaderboard_position,
            row.original.leaderboard_delta,
          )}
        >
          {formatMovementCell(row.original.leaderboard_delta)}
        </span>
      ),
    },
    {
      id: "toPar",
      accessorKey: "total_to_par",
      header: "To par",
      meta: { label: "To par", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => <span className="num">{formatToPar(row.original.total_to_par)}</span>,
    },
    {
      id: "composite",
      accessorKey: "composite",
      header: "Composite",
      meta: { label: "Composite", align: "right", mono: true },
      enableSorting: true,
      cell: ({ row }) => (
        <span className="num">{formatNumber(row.original.composite, 1)}</span>
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
            <div className="pick-primary">
              {m.pick}
              {m.is_new_live_opportunity ? (
                <span className="live-opportunity-badge" aria-label="New live opportunity">
                  NEW LIVE
                </span>
              ) : null}
            </div>
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
            {row.original.is_new_live_opportunity ? (
              <span className="live-opportunity-badge">NEW LIVE</span>
            ) : null}
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
      id: "startPos",
      accessorKey: "startPositionLabel",
      header: "Start pos",
      meta: { label: "Start pos", align: "right", mono: true },
    },
    {
      id: "delta",
      accessorKey: "positionDeltaLabel",
      header: "Pos Δ",
      meta: { label: "Pos Δ", align: "right", mono: true },
      cell: ({ row }) => (
        <span aria-label={row.original.positionDeltaAria ?? undefined}>
          {row.original.positionDeltaLabel ?? "--"}
        </span>
      ),
    },
    {
      id: "toPar",
      accessorKey: "toParLabel",
      header: "To par",
      meta: { label: "To par", align: "right", mono: true },
    },
  ]
}

function formatRankCell(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  return `#${value}`
}

function formatMovementCell(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  if (value === 0) return "0"
  return value > 0 ? `↑${value}` : `↓${Math.abs(value)}`
}

function formatModelDeltaAriaLabel(
  startRank?: number | null,
  currentRank?: number | null,
  delta?: number | null,
) {
  if (startRank === null || startRank === undefined || currentRank === null || currentRank === undefined) {
    return "Model rank movement unavailable"
  }
  if (delta === null || delta === undefined || Number.isNaN(delta)) {
    return `Model rank moved from ${startRank} to ${currentRank}`
  }
  if (delta > 0) {
    return `Model rank improved ${delta} since tee off from ${startRank} to ${currentRank}`
  }
  if (delta < 0) {
    return `Model rank dropped ${Math.abs(delta)} since tee off from ${startRank} to ${currentRank}`
  }
  return `Model rank unchanged at ${currentRank}`
}

function formatScoringDeltaAriaLabel(
  startPos?: string | null,
  currentPos?: string | null,
  delta?: number | null,
) {
  const start = startPos?.trim() || "unknown"
  const current = currentPos?.trim() || "unknown"
  if (delta === null || delta === undefined || Number.isNaN(delta)) {
    return `Scoring position moved from ${start} to ${current}`
  }
  if (delta > 0) {
    return `Scoring position improved ${delta} from ${start} to ${current}`
  }
  if (delta < 0) {
    return `Scoring position fell ${Math.abs(delta)} from ${start} to ${current}`
  }
  return `Scoring position unchanged at ${current}`
}

function formatToPar(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--"
  if (value === 0) return "E"
  return value > 0 ? `+${value}` : `${value}`
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
