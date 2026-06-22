import { useMemo } from "react"
import { Link } from "react-router-dom"

import type { SeasonEventCompareRow } from "@/components/compare/compare-types"
import { buildSeasonEventCompareRows } from "@/components/compare/compare-utils"
import type { GradingSeasonResponse } from "@/lib/types"

const fmt = (v: number | null, digits = 2) => (v == null ? "—" : v.toFixed(digits))
const fmtSigned = (v: number | null, digits = 2) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`

export function CompareSeasonEventsTable({
  season,
  onSelectEvent,
}: {
  season: GradingSeasonResponse | undefined
  onSelectEvent?: (eventId: string) => void
}) {
  const rows = useMemo(() => buildSeasonEventCompareRows(season?.events), [season?.events])
  const summary = season?.summary

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">No per-event grading data yet.</p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {summary ? (
        <div
          className="grid grid-cols-2 gap-3 md:grid-cols-4"
          data-testid="compare-season-aggregate"
        >
          <AggregateTile
            label="Season champ P/L"
            value={fmtSigned(summary.dashboard?.profit ?? null)}
          />
          <AggregateTile
            label="Season chlgr P/L"
            value={fmtSigned(summary.lab?.profit ?? null)}
          />
          <AggregateTile
            label="Season Δ P/L"
            value={fmtSigned(summary.comparison?.profit_delta ?? null)}
          />
          <AggregateTile
            label="Overlap matchups"
            value={String(summary.comparison?.overlap_matchups ?? "—")}
            sub={`${summary.comparison?.picks_only_dashboard ?? 0} champ-only · ${summary.comparison?.picks_only_lab ?? 0} chlgr-only`}
          />
        </div>
      ) : null}

      <div className="compare-table-wrap overflow-x-auto">
        <table className="compare-data-table w-full min-w-[760px] text-sm" data-testid="compare-season-events-table">
          <thead>
            <tr className="text-left text-[var(--text-secondary)]">
              <th className="py-2 pr-4 font-semibold">Event</th>
              <th className="py-2 pr-4 font-semibold num">Champ P/L</th>
              <th className="py-2 pr-4 font-semibold num">Chlgr P/L</th>
              <th className="py-2 pr-4 font-semibold num">Δ P/L</th>
              <th className="py-2 pr-4 font-semibold num">Champ hit%</th>
              <th className="py-2 pr-4 font-semibold num">Chlgr hit%</th>
              <th className="py-2 pr-4 font-semibold num">Overlap</th>
              <th className="py-2 pr-2 font-semibold">Drill down</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <SeasonEventRow key={row.eventId} row={row} onSelectEvent={onSelectEvent} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AggregateTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="compare-kpi-tile rounded-lg border border-[var(--border)] bg-[var(--bg-1)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
        {label}
      </div>
      <div className="num mt-1 text-xl font-semibold text-[var(--text-primary)]">{value}</div>
      {sub ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{sub}</div> : null}
    </div>
  )
}

function SeasonEventRow({
  row,
  onSelectEvent,
}: {
  row: SeasonEventCompareRow
  onSelectEvent?: (eventId: string) => void
}) {
  const deltaCls =
    row.profitDelta == null
      ? ""
      : row.profitDelta > 0
        ? "text-[var(--green)]"
        : row.profitDelta < 0
          ? "text-[var(--red)]"
          : ""

  return (
    <tr className="border-t border-[var(--border)]">
      <td className="py-2 pr-4">
        <div className="font-medium text-[var(--text-primary)]">{row.name}</div>
        {row.eventDate ? (
          <div className="text-xs text-[var(--text-secondary)]">{row.eventDate}</div>
        ) : null}
      </td>
      <td className="py-2 pr-4 num">{fmtSigned(row.championPnl)}</td>
      <td className="py-2 pr-4 num">{fmtSigned(row.challengerPnl)}</td>
      <td className={`py-2 pr-4 num font-medium ${deltaCls}`}>{fmtSigned(row.profitDelta)}</td>
      <td className="py-2 pr-4 num">{fmt(row.championHitRate)}</td>
      <td className="py-2 pr-4 num">{fmt(row.challengerHitRate)}</td>
      <td className="py-2 pr-4 num">{row.overlapMatchups ?? "—"}</td>
      <td className="py-2 pr-2">
        {onSelectEvent ? (
          <button
            type="button"
            className="filter-chip"
            data-testid={`compare-season-drill-${row.eventId}`}
            onClick={() => onSelectEvent(row.eventId)}
          >
            Open event
          </button>
        ) : (
          <Link
            className="filter-chip"
            to={`/compare?event_id=${encodeURIComponent(row.eventId)}`}
            data-testid={`compare-season-link-${row.eventId}`}
          >
            Open event
          </Link>
        )}
      </td>
    </tr>
  )
}
