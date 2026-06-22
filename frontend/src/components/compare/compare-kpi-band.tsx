import type { CompareKpiSummary } from "@/components/compare/compare-types"

const fmt = (v: number | null, digits = 1) => (v == null ? "—" : v.toFixed(digits))

function KpiTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">{label}</div>
      <div className="num text-xl font-semibold text-[var(--text-primary)]">{value}</div>
      {sub ? <div className="text-xs text-[var(--text-faint)]">{sub}</div> : null}
    </div>
  )
}

export function CompareKpiBand({ kpi }: { kpi: CompareKpiSummary }) {
  const maxDelta = kpi.maxDisagreement
  return (
    <section
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
      data-testid="compare-kpi-band"
    >
      <KpiTile
        label="Field"
        value={String(kpi.fieldSize)}
        sub={`${kpi.bothRankedCount} both ranked`}
      />
      <KpiTile label="Mean |Δ rank|" value={fmt(kpi.meanAbsRankDelta)} />
      <KpiTile label="Median |Δ rank|" value={fmt(kpi.medianAbsRankDelta)} />
      <KpiTile
        label="Pick overlap"
        value={`${kpi.overlapBoth}`}
        sub={`${kpi.overlapChampionOnly} champ · ${kpi.overlapChallengerOnly} chlgr only`}
      />
      <KpiTile
        label="Biggest disagreement"
        value={maxDelta ? maxDelta.player : "—"}
        sub={maxDelta ? `Δ ${maxDelta.delta > 0 ? "+" : ""}${maxDelta.delta}` : undefined}
      />
      <KpiTile label="Mode" value={kpi.usingLive ? "Live" : "Upcoming"} sub={kpi.eventName} />
    </section>
  )
}
