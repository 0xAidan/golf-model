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
      <p className="mb-3 text-xs text-[var(--text-faint)]">
        Mean absolute component Δ for players with |rank Δ| ≥ 3 (n={summary.sampleSize})
      </p>
      <ComponentDriversChartLazy summary={summary} />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead>
            <tr className="text-left text-[var(--text-faint)]">
              <th className="py-1 pr-3 font-medium">Player</th>
              <th className="py-1 pr-3 font-medium num">Rank Δ</th>
              <th className="py-1 pr-3 font-medium num">Comp Δ</th>
              <th className="py-1 pr-3 font-medium num">Form Δ</th>
              <th className="py-1 pr-3 font-medium num">Course Δ</th>
            </tr>
          </thead>
          <tbody>
            {topRows.map((row) => (
              <tr key={row.playerKey} className="border-t border-[var(--border)]">
                <td className="max-w-[160px] truncate py-1 pr-3">{row.player}</td>
                <td className="py-1 pr-3 num">{row.rankDelta ?? "—"}</td>
                <td className="py-1 pr-3 num">{fmt(row.compositeDelta)}</td>
                <td className="py-1 pr-3 num">{fmt(row.formDelta)}</td>
                <td className="py-1 pr-3 num">{fmt(row.courseFitDelta)}</td>
              </tr>
            ))}
            {topRows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-2 text-center text-[var(--text-faint)]">
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
