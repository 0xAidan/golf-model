import { useMemo, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { RankScatterChartLazy } from "@/components/compare/compare-charts-lazy"
import { CompareComponentDrivers } from "@/components/compare/compare-component-drivers"
import { CompareDiagnosticsPanel } from "@/components/compare/compare-diagnostics-panel"
import { CompareKpiBand } from "@/components/compare/compare-kpi-band"
import { CompareMatchupDiffTable } from "@/components/compare/compare-matchup-diff-table"
import type { CompareTrackSections } from "@/components/compare/compare-types"
import {
  computeComponentDeltaRows,
  computeKpiSummary,
  computeMatchupDiffRows,
  computeMatchupOverlap,
  computeRankScatterPoints,
} from "@/components/compare/compare-utils"
import { BentoGrid } from "@/components/monitoring/bento-grid"
import { BentoPanel } from "@/components/monitoring/bento-panel"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { api } from "@/lib/api"
import { POLLING } from "@/lib/query-polling"
import type { FieldBoardPlayer } from "@/lib/types"

const fmt = (v?: number | null, d = 1) => (v == null ? "—" : v.toFixed(d))

function CompareFieldBoardSection({
  section,
  highlightedKey,
  onHighlight,
  eventName,
  players,
  isLoading,
  labAvailable,
}: {
  section: "live" | "upcoming"
  highlightedKey: string | null
  onHighlight: (key: string | null) => void
  eventName?: string | null
  players: FieldBoardPlayer[]
  isLoading: boolean
  labAvailable: boolean
}) {
  const [selected, setSelected] = useState<FieldBoardPlayer | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const columns = useMemo<ColumnDef<FieldBoardPlayer, unknown>[]>(() => {
    const cols: ColumnDef<FieldBoardPlayer, unknown>[] = [
      {
        id: "player",
        header: "Player",
        accessorKey: "player",
        cell: ({ row }) => (
          <span
            className={
              row.original.player_key === highlightedKey
                ? "font-semibold text-[var(--gold)]"
                : "text-[var(--text-primary)]"
            }
          >
            {row.original.player}
          </span>
        ),
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
            const cls =
              d > 0 ? "text-[var(--green)]" : d < 0 ? "text-[var(--red)]" : "text-[var(--text-faint)]"
            return <span className={`num ${cls}`}>{d > 0 ? `+${d}` : d}</span>
          },
        },
      )
    }
    cols.push(
      {
        id: "composite",
        header: "Composite",
        accessorFn: (r) => r.composite ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.composite)}</span>,
      },
      {
        id: "form",
        header: "Form",
        accessorFn: (r) => r.form ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.form)}</span>,
      },
      {
        id: "course_fit",
        header: "Course",
        accessorFn: (r) => r.course_fit ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.course_fit)}</span>,
      },
      {
        id: "momentum",
        header: "Mom.",
        accessorFn: (r) => r.momentum ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.momentum, 2)}</span>,
      },
      {
        id: "in_positive_ev",
        header: "+EV",
        accessorFn: (r) => (r.in_positive_ev ? 1 : 0),
        cell: ({ row }) =>
          row.original.in_positive_ev ? (
            <span className="filter-chip active" aria-label="In a positive-EV pick">
              +EV
            </span>
          ) : (
            <span className="text-[var(--text-faint)]">—</span>
          ),
      },
    )
    return cols
  }, [labAvailable, highlightedKey])

  const sortedPlayers = useMemo(
    () =>
      [...players].sort((a, b) => {
        const da = a.rank_delta == null ? -1 : Math.abs(a.rank_delta)
        const db = b.rank_delta == null ? -1 : Math.abs(b.rank_delta)
        return db - da
      }),
    [players],
  )

  const handleRowClick = (row: FieldBoardPlayer) => {
    setSelected(row)
    onHighlight(row.player_key)
    gridRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }

  return (
    <section className="card" ref={gridRef} data-testid="compare-field-board">
      <div className="card-header">
        <div className="card-title">Full field{eventName ? ` — ${eventName}` : ""}</div>
        <div className="text-xs text-[var(--text-faint)]">
          {players.length} players · {section} · sorted by |rank Δ|
        </div>
      </div>
      <div className="card-body">
        {selected ? (
          <div
            className="mb-3 rounded border border-[var(--border)] bg-[var(--bg-1)] px-3 py-2 text-sm"
            data-testid="compare-field-detail"
          >
            <span className="font-medium text-[var(--text-primary)]">{selected.player}</span>
            <span className="ml-2 text-[var(--text-faint)]">
              Champ #{selected.champion_rank ?? "—"} · Chlgr #{selected.challenger_rank ?? "—"} ·
              composite {fmt(selected.composite)} · form {fmt(selected.form)} · course{" "}
              {fmt(selected.course_fit)} · mom {fmt(selected.momentum, 2)}
            </span>
          </div>
        ) : null}
        <ProDataGrid<FieldBoardPlayer>
          data={sortedPlayers}
          columns={columns}
          virtualizeAfter={80}
          stickyHeader
          isLoading={isLoading}
          loadingMessage="Loading field…"
          emptyMessage="No field loaded yet."
          getRowTestId={(row) => `compare-field-row-${row.player_key}`}
          onRowClick={handleRowClick}
          testId="compare-field-grid"
        />
      </div>
    </section>
  )
}

export function CompareEventDashboard({ tracks }: { tracks: CompareTrackSections }) {
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null)
  const section = tracks.usingLive ? "live" : "upcoming"

  const fieldQuery = useQuery({
    queryKey: ["field-board", section],
    queryFn: () => api.getFieldBoard(section),
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const overlap = useMemo(
    () =>
      computeMatchupOverlap(
        tracks.champion?.matchup_bets,
        tracks.challenger?.matchup_bets ?? undefined,
      ),
    [tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets],
  )

  const matchupDiffRows = useMemo(
    () =>
      computeMatchupDiffRows(
        tracks.champion?.matchup_bets,
        tracks.challenger?.matchup_bets ?? undefined,
      ),
    [tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets],
  )

  const componentRows = useMemo(
    () =>
      computeComponentDeltaRows(tracks.champion?.rankings, tracks.challenger?.rankings ?? undefined),
    [tracks.champion?.rankings, tracks.challenger?.rankings],
  )

  const kpi = useMemo(
    () =>
      computeKpiSummary({
        eventName:
          tracks.champion?.event_name ||
          tracks.challenger?.event_name ||
          fieldQuery.data?.event_name ||
          "current event",
        usingLive: tracks.usingLive,
        players: fieldQuery.data?.players ?? [],
        overlap,
      }),
    [tracks, fieldQuery.data, overlap],
  )

  const scatterPoints = useMemo(
    () => computeRankScatterPoints(fieldQuery.data?.players ?? []),
    [fieldQuery.data?.players],
  )

  return (
    <div className="flex flex-col gap-6" data-testid="compare-event-dashboard">
      <CompareKpiBand kpi={kpi} />

      <BentoGrid testId="compare-event-bento">
        <BentoPanel title="Rank disagreement map" span={6} testId="compare-rank-scatter">
          <p className="mb-2 text-xs text-[var(--text-faint)]">
            Each dot is a player. On the diagonal = same rank. Click a dot to highlight in the field
            table.
          </p>
          <RankScatterChartLazy
            points={scatterPoints}
            highlightedKey={highlightedKey}
            onPointClick={(key) => {
              setHighlightedKey(key)
              document
                .querySelector(`[data-testid="compare-field-board"]`)
                ?.scrollIntoView({ behavior: "smooth", block: "nearest" })
            }}
          />
        </BentoPanel>

        <CompareComponentDrivers componentRows={componentRows} />
      </BentoGrid>

      <CompareMatchupDiffTable rows={matchupDiffRows} />

      <CompareFieldBoardSection
        section={section}
        highlightedKey={highlightedKey}
        onHighlight={setHighlightedKey}
        eventName={fieldQuery.data?.event_name}
        players={fieldQuery.data?.players ?? []}
        isLoading={fieldQuery.isLoading}
        labAvailable={fieldQuery.data?.lab_available ?? false}
      />

      <CompareDiagnosticsPanel champion={tracks.champion} challenger={tracks.challenger} />
    </div>
  )
}
