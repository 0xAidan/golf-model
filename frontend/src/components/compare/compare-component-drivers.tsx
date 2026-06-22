import { useMemo } from "react"

import {
  ComponentDriversChartLazy,
} from "@/components/compare/compare-charts-lazy"
import type { ComponentDeltaRow } from "@/components/compare/compare-types"
import {
  computeComponentDriverSummary,
  topComponentDeltaRows,
} from "@/components/compare/compare-utils"
import { BentoPanel } from "@/components/monitoring/bento-panel"

const fmt = (v: number | null, d = 2) => (v == null ? "—" : v.toFixed(d))

export function CompareComponentDrivers({
  componentRows,
}: {
  componentRows: ComponentDeltaRow[]
}) {
  const summary = useMemo(() => computeComponentDriverSummary(componentRows), [componentRows])
  const topRows = useMemo(() => topComponentDeltaRows(componentRows, 10), [componentRows])

  return (
    <BentoPanel title="Component drivers" span={6} testId="compare-component-drivers">
      <p className="compare-panel-desc mb-3 text-sm text-[var(--text-secondary)]">
        Mean absolute component difference for players with |rank Δ| ≥ 3 (sample n={summary.sampleSize})
      </p>
      <ComponentDriversChartLazy summary={summary} />
      <div className="compare-table-wrap mt-4 overflow-x-auto">
        <table className="compare-data-table w-full min-w-[480px] text-sm">
          <thead>
            <tr className="text-left text-[var(--text-secondary)]">
              <th className="py-2 pr-3 font-semibold">Player</th>
              <th className="py-2 pr-3 font-semibold num">Rank Δ</th>
              <th className="py-2 pr-3 font-semibold num">Comp Δ</th>
              <th className="py-2 pr-3 font-semibold num">Form Δ</th>
              <th className="py-2 pr-3 font-semibold num">Course Δ</th>
              <th className="py-2 pr-2 font-semibold num">Mom Δ</th>
            </tr>
          </thead>
          <tbody>
            {topRows.map((row) => (
              <tr key={row.playerKey} className="border-t border-[var(--border)]">
                <td className="max-w-[180px] truncate py-2 pr-3 text-[var(--text-primary)]">{row.player}</td>
                <td className="py-2 pr-3 num">{row.rankDelta ?? "—"}</td>
                <td className="py-2 pr-3 num">{fmt(row.compositeDelta)}</td>
                <td className="py-2 pr-3 num">{fmt(row.formDelta)}</td>
                <td className="py-2 pr-3 num">{fmt(row.courseFitDelta)}</td>
                <td className="py-2 pr-2 num">{fmt(row.momentumDelta, 3)}</td>
              </tr>
            ))}
            {topRows.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-3 text-center text-[var(--text-secondary)]">
                  No component deltas to show.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </BentoPanel>
  )
}
