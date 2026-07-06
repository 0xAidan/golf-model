import { useMemo, useState } from "react"
import type { ColumnDef } from "@tanstack/react-table"

import type { GradedPickDiffRow, MatchupBucket } from "@/components/compare/compare-types"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { PickRow } from "@/components/ui/pick-row"
import type { MatchupBet, TrackRecordPick } from "@/lib/types"

const BUCKETS: { id: MatchupBucket; label: string }[] = [
  { id: "both", label: "Both" },
  { id: "champion_only", label: "Champion only" },
  { id: "challenger_only", label: "Challenger only" },
]

const fmt = (v: number | null, digits = 2) => (v == null ? "—" : v.toFixed(digits))
const fmtHit = (v: boolean | null) => (v == null ? "—" : v ? "W" : "L")

function toPickRowBet(pick: TrackRecordPick): MatchupBet {
  return {
    pick: pick.player_display,
    pick_key: pick.player_key ?? pick.player_display,
    opponent: pick.opponent_display ?? "—",
    opponent_key: pick.opponent_key ?? pick.opponent_display ?? "",
    odds: pick.market_odds ?? "—",
    book: pick.market_book ?? undefined,
    model_win_prob: pick.model_prob ?? Number.NaN,
    implied_prob: Number.NaN,
    ev: pick.ev ?? Number.NaN,
    ev_pct: "",
    composite_gap: Number.NaN,
    form_gap: Number.NaN,
    course_fit_gap: Number.NaN,
    reason: pick.reasoning ?? "",
    market_type: pick.market_type ?? pick.bet_type,
    graded_result:
      pick.outcome === "win" || pick.outcome === "loss" || pick.outcome === "push"
        ? pick.outcome
        : undefined,
  }
}

export function CompareGradedPicksTable({ rows }: { rows: GradedPickDiffRow[] }) {
  const [bucket, setBucket] = useState<MatchupBucket>("both")
  const filtered = useMemo(() => rows.filter((row) => row.bucket === bucket), [rows, bucket])

  const columns = useMemo<ColumnDef<GradedPickDiffRow, unknown>[]>(
    () => [
      {
        id: "pick",
        header: "Pick",
        accessorKey: "key",
        meta: { label: "Pick", sticky: true },
        cell: ({ row }) => <PickRow bet={toPickRowBet(row.original.sourcePick)} gradedResult={row.original.sourcePick.outcome} />,
      },
      {
        id: "championProfit",
        header: "Champ P/L",
        accessorFn: (r) => r.championProfit ?? -999,
        meta: { label: "Champ P/L", align: "right", mono: true },
        cell: ({ row }) => {
          const v = row.original.championProfit
          if (v == null) return <span className="num text-[var(--text-faint)]">—</span>
          const cls = v > 0 ? "text-[var(--green)]" : v < 0 ? "text-[var(--red)]" : ""
          return <span className={`num ${cls}`}>{v > 0 ? "+" : ""}{fmt(v)}u</span>
        },
      },
      {
        id: "challengerProfit",
        header: "Chlgr P/L",
        accessorFn: (r) => r.challengerProfit ?? -999,
        meta: { label: "Chlgr P/L", align: "right", mono: true },
        cell: ({ row }) => {
          const v = row.original.challengerProfit
          if (v == null) return <span className="num text-[var(--text-faint)]">—</span>
          const cls = v > 0 ? "text-[var(--green)]" : v < 0 ? "text-[var(--red)]" : ""
          return <span className={`num ${cls}`}>{v > 0 ? "+" : ""}{fmt(v)}u</span>
        },
      },
      {
        id: "championHit",
        header: "Champ",
        accessorKey: "championHit",
        meta: { label: "Champ", align: "center", mono: true },
        cell: ({ row }) => <span className="num">{fmtHit(row.original.championHit)}</span>,
      },
      {
        id: "challengerHit",
        header: "Chlgr",
        accessorKey: "challengerHit",
        meta: { label: "Chlgr", align: "center", mono: true },
        cell: ({ row }) => <span className="num">{fmtHit(row.original.challengerHit)}</span>,
      },
      {
        id: "championEv",
        header: "Champ EV",
        accessorFn: (r) => r.championEv ?? -999,
        meta: { label: "Champ EV", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmt(row.original.championEv, 3)}</span>,
      },
      {
        id: "challengerEv",
        header: "Chlgr EV",
        accessorFn: (r) => r.challengerEv ?? -999,
        meta: { label: "Chlgr EV", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmt(row.original.challengerEv, 3)}</span>,
      },
    ],
    [],
  )

  if (rows.length === 0) return null

  return (
    <section className="card compare-panel" data-testid="compare-graded-picks">
      <div className="card-header flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="card-title">Graded picks</div>
          <div className="text-xs text-[var(--text-secondary)]">
            Official scored +EV picks with outcomes for both tracks
          </div>
        </div>
        <div className="flex gap-2" role="group" aria-label="Graded pick overlap bucket">
          {BUCKETS.map((b) => (
            <button
              key={b.id}
              type="button"
              className={`filter-chip${bucket === b.id ? " active" : ""}`}
              aria-pressed={bucket === b.id}
              data-testid={`compare-graded-bucket-${b.id}`}
              onClick={() => setBucket(b.id)}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card-body">
        <ProDataGrid<GradedPickDiffRow>
          data={filtered}
          columns={columns}
          virtualizeAfter={40}
          stickyHeader
          emptyMessage="No graded picks in this bucket."
          getRowTestId={(row) => `compare-graded-row-${row.key}`}
          testId="compare-graded-grid"
        />
      </div>
    </section>
  )
}
