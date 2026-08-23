import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { Reveal, Stagger, StaggerItem } from "@/components/motion/primitives"
import { SkeletonNumber, SkeletonPanelRows } from "@/components/motion/skeletons"
import { api } from "@/lib/api"
import type { PlayerBettingRecord } from "@/lib/types"

/**
 * BettingRecordTab — "what has the model said about this player,
 * and was it right?" Units P/L headline numeral, hit-rate dial,
 * per-market breakdown bars, recent graded picks.
 */
export function BettingRecordTab({ playerKey }: { playerKey: string }) {
  const query = useQuery({
    queryKey: ["redesign-betting-record", playerKey],
    queryFn: () => api.redesign.bettingRecord(playerKey),
    staleTime: 60_000,
  })

  if (query.isLoading) {
    return (
      <div className="panel p-5" data-testid="betting-record-loading">
        <SkeletonNumber />
        <div className="mt-4">
          <SkeletonPanelRows rows={3} />
        </div>
      </div>
    )
  }

  if (query.isError || !query.data) {
    return (
      <div className="panel p-5 text-sm text-[var(--text-muted)]" data-testid="betting-record-error">
        Betting record is unavailable right now.
      </div>
    )
  }

  return <BettingRecordView record={query.data} />
}

function fmtSigned(value: number, digits = 2): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`
}

function BettingRecordView({ record }: { record: PlayerBettingRecord }) {
  const hasGraded = record.graded_picks > 0

  const marketRows = useMemo(
    () =>
      Object.entries(record.by_market).sort((a, b) => b[1].n - a[1].n),
    [record.by_market],
  )
  const maxMarketN = Math.max(1, ...marketRows.map(([, m]) => m.n))

  return (
    <Stagger className="flex flex-col gap-4">
      <StaggerItem>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            label="Units P/L"
            value={hasGraded ? fmtSigned(record.units_profit) : "—"}
            tone={record.units_profit > 0 ? "positive" : record.units_profit < 0 ? "negative" : "neutral"}
            testId="br-units-pl"
          />
          <StatTile label="Hit rate" value={hasGraded && record.hit_rate != null ? `${(record.hit_rate * 100).toFixed(1)}%` : "—"} testId="br-hit-rate" />
          <StatTile label="Graded picks" value={String(record.graded_picks)} sub={`${record.total_picks} generated`} />
          <StatTile label="Avg edge" value={record.avg_ev != null ? `+${(record.avg_ev * 100).toFixed(1)}%` : "—"} />
        </div>
      </StaggerItem>

      {marketRows.length > 0 ? (
        <StaggerItem>
          <div className="panel">
            <div className="panel__header">
              <span className="panel__title">By market</span>
            </div>
            <div className="panel__body flex flex-col gap-3">
              {marketRows.map(([market, stats]) => (
                <div key={market} className="flex items-center gap-3 text-sm" data-testid={`br-market-${market}`}>
                  <span className="w-24 shrink-0 capitalize text-[var(--text-secondary)]">{market.replace(/_/g, " ")}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--text-faint)_14%,transparent)]">
                    <div
                      className="h-full rounded-full bg-[var(--chart-c2)]"
                      style={{ width: `${(stats.n / maxMarketN) * 100}%` }}
                    />
                  </div>
                  <span className="num w-28 text-right text-xs text-[var(--text-muted)]">
                    {stats.hits}/{stats.n} ·{" "}
                    <span className={stats.profit >= 0 ? "text-[var(--accent-edge)]" : "text-[var(--red)]"}>
                      {fmtSigned(stats.profit)}u
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </StaggerItem>
      ) : null}

      <StaggerItem>
        <div className="panel">
          <div className="panel__header">
            <span className="panel__title">Recent graded picks</span>
          </div>
          {record.recent.length === 0 ? (
            <p className="p-5 text-sm text-[var(--text-muted)]">
              No graded picks yet for this player.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--divider)]" data-testid="br-recent-list">
              {record.recent.map((pick, index) => {
                const won = pick.hit === 1
                const lost = pick.hit === 0
                return (
                  <li key={index} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                    <Reveal className="contents" key={`${index}-${pick.created_at}`}>
                      <span
                        className={
                          won
                            ? "rounded-full border border-[color-mix(in_srgb,var(--green)_35%,transparent)] bg-[var(--green-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--green)]"
                            : lost
                              ? "rounded-full border border-[color-mix(in_srgb,var(--red)_35%,transparent)] bg-[var(--red-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--red)]"
                              : "rounded-full border border-[var(--border)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]"
                        }
                      >
                        {won ? "W" : lost ? "L" : "—"}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[var(--text)]">
                        {pick.bet_type?.replace(/_/g, " ") ?? "Matchup"}
                        {pick.opponent_display ? <> vs {pick.opponent_display}</> : null}
                      </span>
                      <span className="num text-xs text-[var(--text-muted)]">{pick.market_odds ?? ""}</span>
                      <span
                        className={
                          (pick.profit ?? 0) >= 0
                            ? "num w-16 text-right text-xs text-[var(--accent-edge)]"
                            : "num w-16 text-right text-xs text-[var(--red)]"
                        }
                      >
                        {fmtSigned(pick.profit ?? 0)}
                      </span>
                    </Reveal>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </StaggerItem>
    </Stagger>
  )
}

function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
  testId,
}: {
  label: string
  value: string
  sub?: string
  tone?: "positive" | "negative" | "neutral"
  testId?: string
}) {
  return (
    <div className="panel px-4 py-3" data-testid={testId}>
      <div className="text-[11px] font-medium tracking-wide text-[var(--text-muted)]">{label}</div>
      <div
        className={
          tone === "positive"
            ? "display-num display-num--sm display-num--positive mt-1"
            : tone === "negative"
              ? "display-num display-num--sm display-num--negative mt-1"
              : "display-num display-num--sm mt-1"
        }
      >
        {value}
      </div>
      {sub ? <div className="mt-1 text-[10px] text-[var(--text-faint)]">{sub}</div> : null}
    </div>
  )
}
