import type { CompareKpiSummary } from "@/components/compare/compare-types"

const fmt = (v: number | null, digits = 1) => (v == null ? "—" : v.toFixed(digits))
const fmtSigned = (v: number | null, digits = 2) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`

function KpiTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="compare-kpi-tile rounded-lg border border-[var(--border)] bg-[var(--bg-1)] px-4 py-3 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
        {label}
      </div>
      <div className="num mt-1 text-2xl font-semibold leading-tight text-[var(--text-primary)]">
        {value}
      </div>
      {sub ? <div className="mt-1 text-xs leading-snug text-[var(--text-secondary)]">{sub}</div> : null}
    </div>
  )
}

export function CompareKpiBand({ kpi }: { kpi: CompareKpiSummary }) {
  const maxDelta = kpi.maxDisagreement
  const showGraded =
    kpi.championGradedPnl != null ||
    kpi.challengerGradedPnl != null ||
    kpi.gradedProfitDelta != null

  return (
    <section
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6"
      data-testid="compare-kpi-band"
    >
      <KpiTile
        label="Field"
        value={String(kpi.fieldSize)}
        sub={`${kpi.bothRankedCount} ranked on both tracks`}
      />
      <KpiTile label="Mean |Δ rank|" value={fmt(kpi.meanAbsRankDelta)} />
      <KpiTile label="Median |Δ rank|" value={fmt(kpi.medianAbsRankDelta)} />
      <KpiTile
        label="Model pick overlap"
        value={`${kpi.overlapBoth}`}
        sub={`${kpi.overlapChampionOnly} champ · ${kpi.overlapChallengerOnly} chlgr only`}
      />
      <KpiTile
        label="Biggest rank split"
        value={maxDelta ? maxDelta.player : "—"}
        sub={maxDelta ? `Δ ${maxDelta.delta > 0 ? "+" : ""}${maxDelta.delta}` : undefined}
      />
      {showGraded ? (
        <KpiTile
          label="Graded P/L delta"
          value={fmtSigned(kpi.gradedProfitDelta ?? null)}
          sub={`Champ ${fmtSigned(kpi.championGradedPnl ?? null)}u · Chlgr ${fmtSigned(kpi.challengerGradedPnl ?? null)}u`}
        />
      ) : (
        <KpiTile label="Mode" value={kpi.modeLabel} sub={kpi.eventName} />
      )}
      {showGraded ? (
        <KpiTile
          label="Event"
          value={kpi.modeLabel}
          sub={kpi.eventName}
        />
      ) : null}
    </section>
  )
}
