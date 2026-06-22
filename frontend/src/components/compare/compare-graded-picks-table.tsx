import { useMemo, useState } from "react"
import type { ColumnDef } from "@tanstack/react-table"

import type { GradedPickDiffRow, MatchupBucket } from "@/components/compare/compare-types"
import { ProDataGrid } from "@/components/ui/pro-data-grid"

const BUCKETS: { id: MatchupBucket; label: string }[] = [
  { id: "both", label: "Both" },
  { id: "champion_only", label: "Champion only" },
  { id: "challenger_only", label: "Challenger only" },
]

const fmt = (v: number | null, digits = 2) => (v == null ? "—" : v.toFixed(digits))
const fmtHit = (v: boolean | null) => (v == null ? "—" : v ? "W" : "L")

export function CompareGradedPicksTable({ rows }: { rows: GradedPickDiffRow[] }) {
  const [bucket, setBucket] = useState<MatchupBucket>("both")
  const filtered = useMemo(() => rows.filter((row) => row.bucket === bucket), [rows, bucket])

  const columns = useMemo<ColumnDef<GradedPickDiffRow, unknown>[]>(
    () => [
      { id: "pick", header: "Pick", accessorKey: "pick" },
      { id: "opponent", header: "Opponent", accessorKey: "opponent" },
      { id: "betType", header: "Market", accessorKey: "betType" },
      { id: "book", header: "Book", accessorKey: "book" },
      {
        id: "championProfit",
        header: "Champ P/L",
        accessorFn: (r) => r.championProfit ?? -999,
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
        cell: ({ row }) => <span className="num">{fmtHit(row.original.championHit)}</span>,
      },
      {
        id: "challengerHit",
        header: "Chlgr",
        accessorKey: "challengerHit",
        cell: ({ row }) => <span className="num">{fmtHit(row.original.challengerHit)}</span>,
      },
      {
        id: "championEv",
        header: "Champ EV",
        accessorFn: (r) => r.championEv ?? -999,
        cell: ({ row }) => <span className="num">{fmt(row.original.championEv, 3)}</span>,
      },
      {
        id: "challengerEv",
        header: "Chlgr EV",
        accessorFn: (r) => r.challengerEv ?? -999,
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
