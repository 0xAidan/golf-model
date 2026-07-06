import { useMemo, useState } from "react"
import type { ColumnDef } from "@tanstack/react-table"

import type { MatchupBucket, MatchupDiffRow } from "@/components/compare/compare-types"
import { filterMatchupDiffRows } from "@/components/compare/compare-utils"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { PickRow } from "@/components/ui/pick-row"

const BUCKETS: { id: MatchupBucket; label: string }[] = [
  { id: "both", label: "Both" },
  { id: "champion_only", label: "Champion only" },
  { id: "challenger_only", label: "Challenger only" },
]

const fmtEv = (v: number | null) => (v == null ? "—" : v.toFixed(3))
const fmtProb = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`)

export function CompareMatchupDiffTable({ rows }: { rows: MatchupDiffRow[] }) {
  const [bucket, setBucket] = useState<MatchupBucket>("both")
  const filtered = useMemo(() => filterMatchupDiffRows(rows, bucket), [rows, bucket])

  const columns = useMemo<ColumnDef<MatchupDiffRow, unknown>[]>(
    () => [
      {
        id: "pick",
        header: "Pick",
        accessorKey: "key",
        meta: { label: "Pick", sticky: true },
        cell: ({ row }) => (
          <PickRow bet={row.original.sourceBet} />
        ),
      },
      {
        id: "championEv",
        header: "Champ EV",
        accessorFn: (r) => r.championEv ?? -999,
        meta: { label: "Champ EV", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmtEv(row.original.championEv)}</span>,
      },
      {
        id: "challengerEv",
        header: "Chlgr EV",
        accessorFn: (r) => r.challengerEv ?? -999,
        meta: { label: "Chlgr EV", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmtEv(row.original.challengerEv)}</span>,
      },
      {
        id: "evDelta",
        header: "Δ EV",
        accessorFn: (r) => Math.abs(r.evDelta ?? 0),
        meta: { label: "EV delta", align: "right", mono: true },
        cell: ({ row }) => {
          const d = row.original.evDelta
          if (d == null) return <span className="num text-[var(--text-faint)]">—</span>
          const cls = d > 0 ? "text-[var(--green)]" : d < 0 ? "text-[var(--red)]" : ""
          return (
            <span className={`num ${cls}`}>
              {d > 0 ? "+" : ""}
              {d.toFixed(3)}
            </span>
          )
        },
      },
      {
        id: "championProb",
        header: "Champ prob",
        accessorFn: (r) => r.championProb ?? 0,
        meta: { label: "Champ prob", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmtProb(row.original.championProb)}</span>,
      },
      {
        id: "challengerProb",
        header: "Chlgr prob",
        accessorFn: (r) => r.challengerProb ?? 0,
        meta: { label: "Chlgr prob", align: "right", mono: true },
        cell: ({ row }) => <span className="num">{fmtProb(row.original.challengerProb)}</span>,
      },
    ],
    [],
  )

  return (
    <section className="card compare-panel" data-testid="compare-matchup-diff">
      <div className="card-header flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="card-title">Model pick diff</div>
          <div className="text-xs text-[var(--text-secondary)]">
            +EV matchup lines each track would take at snapshot time
          </div>
        </div>
        <div className="flex gap-2" role="group" aria-label="Matchup overlap bucket">
          {BUCKETS.map((b) => (
            <button
              key={b.id}
              type="button"
              className={`filter-chip${bucket === b.id ? " active" : ""}`}
              aria-pressed={bucket === b.id}
              data-testid={`compare-matchup-bucket-${b.id}`}
              onClick={() => setBucket(b.id)}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
      <div className="card-body">
        <ProDataGrid<MatchupDiffRow>
          data={filtered}
          columns={columns}
          virtualizeAfter={40}
          stickyHeader
          emptyMessage="No matchups in this bucket."
          getRowTestId={(row) => `compare-matchup-row-${row.key}`}
          testId="compare-matchup-grid"
        />
      </div>
    </section>
  )
}
