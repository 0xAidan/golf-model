import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { api } from "@/lib/api"
import { POLLING } from "@/lib/query-polling"
import type { FieldBoardPlayer } from "@/lib/types"

const fmt = (v?: number | null, d = 1) => (v == null ? "—" : v.toFixed(d))

/**
 * Field-complete board: every entrant in one virtualized, sortable table with both-track
 * ranks (champion vs challenger), composite components, and pick involvement. Clicking a
 * row selects the player for the deep profile below.
 */
export function FieldBoardPanel({
  onSelect,
  section = "auto",
}: {
  onSelect?: (playerKey: string, playerDisplay: string) => void
  section?: "auto" | "live" | "upcoming"
}) {
  const query = useQuery({
    queryKey: ["field-board", section],
    queryFn: () => api.getFieldBoard(section),
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const labAvailable = query.data?.lab_available ?? false

  const columns = useMemo<ColumnDef<FieldBoardPlayer, unknown>[]>(() => {
    const cols: ColumnDef<FieldBoardPlayer, unknown>[] = [
      {
        id: "player",
        header: "Player",
        accessorKey: "player",
        cell: ({ row }) => <span className="text-[var(--text-primary)]">{row.original.player}</span>,
      },
      {
        id: "champion_rank",
        header: "Champ #",
        accessorFn: (r) => r.champion_rank ?? Number.MAX_SAFE_INTEGER,
        cell: ({ row }) => <span className="num">{row.original.champion_rank ?? "—"}</span>,
      },
    ]
    if (labAvailable) {
      cols.push(
        {
          id: "challenger_rank",
          header: "Chlgr #",
          accessorFn: (r) => r.challenger_rank ?? Number.MAX_SAFE_INTEGER,
          cell: ({ row }) => <span className="num">{row.original.challenger_rank ?? "—"}</span>,
        },
        {
          id: "rank_delta",
          header: "Δ",
          accessorFn: (r) => (r.rank_delta == null ? 0 : Math.abs(r.rank_delta)),
          cell: ({ row }) => {
            const d = row.original.rank_delta
            if (d == null) return <span className="num text-[var(--text-faint)]">—</span>
            const cls = d > 0 ? "text-[var(--green)]" : d < 0 ? "text-[var(--red)]" : "text-[var(--text-faint)]"
            return <span className={`num ${cls}`}>{d > 0 ? `+${d}` : d}</span>
          },
        },
      )
    }
    cols.push(
      { id: "composite", header: "Composite", accessorFn: (r) => r.composite ?? 0, cell: ({ row }) => <span className="num">{fmt(row.original.composite)}</span> },
      { id: "form", header: "Form", accessorFn: (r) => r.form ?? 0, cell: ({ row }) => <span className="num">{fmt(row.original.form)}</span> },
      { id: "course_fit", header: "Course", accessorFn: (r) => r.course_fit ?? 0, cell: ({ row }) => <span className="num">{fmt(row.original.course_fit)}</span> },
      { id: "momentum", header: "Mom.", accessorFn: (r) => r.momentum ?? 0, cell: ({ row }) => <span className="num">{fmt(row.original.momentum, 2)}</span> },
      { id: "matchup_count", header: "Matchups", accessorFn: (r) => r.matchup_count, cell: ({ row }) => <span className="num">{row.original.matchup_count || "—"}</span> },
      {
        id: "in_positive_ev",
        header: "+EV",
        accessorFn: (r) => (r.in_positive_ev ? 1 : 0),
        cell: ({ row }) =>
          row.original.in_positive_ev ? (
            <span className="filter-chip active" aria-label="In a positive-EV pick">+EV</span>
          ) : (
            <span className="text-[var(--text-faint)]">—</span>
          ),
      },
    )
    return cols
  }, [labAvailable])

  if (query.isError) {
    return (
      <div className="card" data-testid="field-board-error">
        <div className="card-body text-sm text-[var(--text-secondary)]">
          Field board unavailable. Ensure the live-refresh snapshot has a current field.
        </div>
      </div>
    )
  }

  const players = query.data?.players ?? []

  return (
    <section className="card" data-testid="field-board-panel">
      <div className="card-header">
        <div className="card-title">
          Field board{query.data?.event_name ? ` — ${query.data.event_name}` : ""}
        </div>
        <div className="text-xs text-[var(--text-faint)]">
          {query.data?.player_count ?? 0} players · {query.data?.section ?? "—"}
          {labAvailable ? " · champion vs challenger" : " · champion only (lab lane off)"}
        </div>
      </div>
      <div className="card-body">
        <ProDataGrid<FieldBoardPlayer>
          data={players}
          columns={columns}
          virtualizeAfter={80}
          stickyHeader
          isLoading={query.isLoading}
          loadingMessage="Loading field…"
          emptyMessage="No field loaded yet. Field appears once the live-refresh snapshot has an event."
          getRowTestId={(row) => `field-board-row-${row.player_key}`}
          onRowClick={(row) => onSelect?.(row.player_key, row.player)}
          testId="field-board-grid"
        />
      </div>
    </section>
  )
}
