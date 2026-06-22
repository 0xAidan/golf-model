import { useMemo, useRef, useState } from "react"
import type { ColumnDef } from "@tanstack/react-table"

import { RankScatterChartLazy } from "@/components/compare/compare-charts-lazy"
import { CompareComponentDrivers } from "@/components/compare/compare-component-drivers"
import { CompareDiagnosticsPanel } from "@/components/compare/compare-diagnostics-panel"
import { CompareGradedPicksTable } from "@/components/compare/compare-graded-picks-table"
import { CompareKpiBand } from "@/components/compare/compare-kpi-band"
import { CompareMatchupDiffTable } from "@/components/compare/compare-matchup-diff-table"
import type {
  CompareEventMode,
  CompareFieldPlayer,
  CompareTrackSections,
} from "@/components/compare/compare-types"
import {
  computeComponentDeltaRows,
  computeGradedPickDiffRows,
  computeKpiSummary,
  computeMatchupDiffRows,
  computeMatchupOverlap,
  computeRankScatterPoints,
  resolveSnapshotRankings,
} from "@/components/compare/compare-utils"
import { BentoGrid } from "@/components/monitoring/bento-grid"
import { BentoPanel } from "@/components/monitoring/bento-panel"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import type { GradingSeasonEvent } from "@/lib/types"

const fmt = (v?: number | null, d = 1) => (v == null ? "—" : v.toFixed(d))

function CompareFieldBoardSection({
  eventName,
  modeLabel,
  players,
  isLoading,
  labAvailable,
  highlightedKey,
  onHighlight,
}: {
  eventName: string
  modeLabel: string
  players: CompareFieldPlayer[]
  isLoading: boolean
  labAvailable: boolean
  highlightedKey: string | null
  onHighlight: (key: string | null) => void
}) {
  const [selected, setSelected] = useState<CompareFieldPlayer | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const columns = useMemo<ColumnDef<CompareFieldPlayer, unknown>[]>(() => {
    const cols: ColumnDef<CompareFieldPlayer, unknown>[] = [
      {
        id: "player",
        header: "Player",
        accessorKey: "player",
        cell: ({ row }) => (
          <span
            className={
              row.original.player_key === highlightedKey
                ? "font-semibold text-[var(--gold)]"
                : "font-medium text-[var(--text-primary)]"
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
          header: "Rank Δ",
          accessorFn: (r) => (r.rank_delta == null ? 0 : Math.abs(r.rank_delta)),
          cell: ({ row }) => {
            const d = row.original.rank_delta
            if (d == null) return <span className="num text-[var(--text-faint)]">—</span>
            const cls =
              d > 0 ? "text-[var(--green)]" : d < 0 ? "text-[var(--red)]" : "text-[var(--text-faint)]"
            return <span className={`num font-medium ${cls}`}>{d > 0 ? `+${d}` : d}</span>
          },
        },
        {
          id: "composite_delta",
          header: "Comp Δ",
          accessorFn: (r) =>
            r.champion_composite != null && r.challenger_composite != null
              ? Math.abs(r.champion_composite - r.challenger_composite)
              : 0,
          cell: ({ row }) => {
            const a = row.original.champion_composite
            const b = row.original.challenger_composite
            if (a == null || b == null) return <span className="num">—</span>
            const d = a - b
            const cls = d > 0 ? "text-[var(--green)]" : d < 0 ? "text-[var(--red)]" : ""
            return <span className={`num ${cls}`}>{d > 0 ? "+" : ""}{d.toFixed(2)}</span>
          },
        },
        {
          id: "form_delta",
          header: "Form Δ",
          accessorFn: (r) =>
            r.champion_form != null && r.challenger_form != null
              ? Math.abs(r.champion_form - r.challenger_form)
              : 0,
          cell: ({ row }) => {
            const a = row.original.champion_form
            const b = row.original.challenger_form
            if (a == null || b == null) return <span className="num">—</span>
            const d = a - b
            return <span className="num">{d > 0 ? "+" : ""}{d.toFixed(2)}</span>
          },
        },
        {
          id: "course_delta",
          header: "Course Δ",
          accessorFn: (r) =>
            r.champion_course_fit != null && r.challenger_course_fit != null
              ? Math.abs(r.champion_course_fit - r.challenger_course_fit)
              : 0,
          cell: ({ row }) => {
            const a = row.original.champion_course_fit
            const b = row.original.challenger_course_fit
            if (a == null || b == null) return <span className="num">—</span>
            const d = a - b
            return <span className="num">{d > 0 ? "+" : ""}{d.toFixed(2)}</span>
          },
        },
      )
    }
    cols.push(
      {
        id: "champion_composite",
        header: "Champ comp",
        accessorFn: (r) => r.champion_composite ?? r.composite ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.champion_composite ?? row.original.composite)}</span>,
      },
      {
        id: "challenger_composite",
        header: "Chlgr comp",
        accessorFn: (r) => r.challenger_composite ?? 0,
        cell: ({ row }) => <span className="num">{fmt(row.original.challenger_composite)}</span>,
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
  }, [highlightedKey, labAvailable])

  const sortedPlayers = useMemo(
    () =>
      [...players].sort((a, b) => {
        const da = a.rank_delta == null ? -1 : Math.abs(a.rank_delta)
        const db = b.rank_delta == null ? -1 : Math.abs(b.rank_delta)
        return db - da
      }),
    [players],
  )

  const handleRowClick = (row: CompareFieldPlayer) => {
    setSelected(row)
    onHighlight(row.player_key)
    gridRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }

  return (
    <section className="card compare-panel" ref={gridRef} data-testid="compare-field-board">
      <div className="card-header">
        <div className="card-title">Full field — {eventName}</div>
        <div className="text-xs text-[var(--text-secondary)]">
          {players.length} players · {modeLabel} · sorted by |rank Δ|
        </div>
      </div>
      <div className="card-body">
        {selected ? (
          <div
            className="compare-detail-strip mb-3 rounded-lg border border-[var(--border)] bg-[var(--bg-1)] px-4 py-3 text-sm"
            data-testid="compare-field-detail"
          >
            <div className="font-semibold text-[var(--text-primary)]">{selected.player}</div>
            <div className="mt-1 grid gap-1 text-[var(--text-secondary)] sm:grid-cols-2">
              <span>Champ #{selected.champion_rank ?? "—"} · Chlgr #{selected.challenger_rank ?? "—"} · rank Δ {selected.rank_delta ?? "—"}</span>
              <span>
                Comp {fmt(selected.champion_composite)} vs {fmt(selected.challenger_composite)} · Form{" "}
                {fmt(selected.champion_form)} vs {fmt(selected.challenger_form)} · Course{" "}
                {fmt(selected.champion_course_fit)} vs {fmt(selected.challenger_course_fit)}
              </span>
            </div>
          </div>
        ) : null}
        <ProDataGrid<CompareFieldPlayer>
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

export function CompareEventDashboard({
  tracks,
  players,
  gradingEvent,
  eventName,
  eventMode,
  modeLabel,
  isLoading,
  labAvailable,
}: {
  tracks: CompareTrackSections
  players: CompareFieldPlayer[]
  gradingEvent?: GradingSeasonEvent
  eventName: string
  eventMode: CompareEventMode
  modeLabel: string
  isLoading: boolean
  labAvailable: boolean
}) {
  const [highlightedKey, setHighlightedKey] = useState<string | null>(null)

  const championRankings = resolveSnapshotRankings(tracks.champion)
  const challengerRankings = resolveSnapshotRankings(tracks.challenger)

  const overlap = useMemo(
    () => computeMatchupOverlap(tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets ?? undefined),
    [tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets],
  )

  const matchupDiffRows = useMemo(
    () => computeMatchupDiffRows(tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets ?? undefined),
    [tracks.champion?.matchup_bets, tracks.challenger?.matchup_bets],
  )

  const gradedPickRows = useMemo(
    () =>
      computeGradedPickDiffRows(
        gradingEvent?.lanes?.dashboard?.picks,
        gradingEvent?.lanes?.lab?.picks,
      ),
    [gradingEvent],
  )

  const componentRows = useMemo(
    () => computeComponentDeltaRows(championRankings, challengerRankings),
    [championRankings, challengerRankings],
  )

  const kpi = useMemo(
    () =>
      computeKpiSummary({
        eventName,
        eventMode,
        modeLabel,
        usingLive: tracks.usingLive,
        players,
        overlap,
        championGradedPnl: gradingEvent?.lanes?.dashboard?.record?.profit ?? gradingEvent?.lanes?.dashboard?.total_profit,
        challengerGradedPnl: gradingEvent?.lanes?.lab?.record?.profit ?? gradingEvent?.lanes?.lab?.total_profit,
        gradedProfitDelta: gradingEvent?.comparison?.profit_delta,
      }),
    [eventMode, eventName, gradingEvent, modeLabel, overlap, players, tracks.usingLive],
  )

  const scatterPoints = useMemo(() => computeRankScatterPoints(players), [players])

  return (
    <div className="compare-dashboard flex flex-col gap-6" data-testid="compare-event-dashboard">
      <CompareKpiBand kpi={kpi} />

      <BentoGrid testId="compare-event-bento">
        <BentoPanel title="Rank disagreement map" span={6} testId="compare-rank-scatter">
          <p className="compare-panel-desc mb-3 text-sm text-[var(--text-secondary)]">
            Each dot is a player. On the diagonal = same rank. Farther from the line = bigger split.
            Click a dot to highlight that player below.
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

      {gradedPickRows.length > 0 ? <CompareGradedPicksTable rows={gradedPickRows} /> : null}

      <CompareFieldBoardSection
        eventName={eventName}
        modeLabel={modeLabel}
        players={players}
        isLoading={isLoading}
        labAvailable={labAvailable}
        highlightedKey={highlightedKey}
        onHighlight={setHighlightedKey}
      />

      <CompareDiagnosticsPanel champion={tracks.champion} challenger={tracks.challenger} />
    </div>
  )
}
