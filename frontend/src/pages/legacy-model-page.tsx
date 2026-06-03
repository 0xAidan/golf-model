import { Link } from "react-router-dom"

import { DataTable } from "@/components/ui/data-table"
import { PageHeader } from "@/components/ui/page-header"
import type { LiveRefreshSnapshot } from "@/lib/types"

export function LegacyModelPage({ liveSnapshot }: { liveSnapshot: LiveRefreshSnapshot | null }) {
  const legacy = liveSnapshot?.legacy_tournament
  const rankings = legacy?.rankings ?? []
  const matchupBets = legacy?.matchup_bets_all_books ?? legacy?.matchup_bets ?? []
  const diagnosticsErrors = legacy?.diagnostics?.errors ?? []

  return (
    <div className="research-page">
      <PageHeader
        eyebrow="Research"
        title="Legacy model (baseline)"
        description="Read-only fallback lane for last month's baseline model."
        action={
          <Link to="/" className="btn btn-ghost btn-sm">
            Back to cockpit
          </Link>
        }
      />

      <div className="card research-card">
        <div className="card-body research-card-body">
          {!legacy ? (
            <div className="term-notice">
              Legacy baseline snapshot is not available yet. Refresh the live snapshot and try again.
            </div>
          ) : (
            <>
              <div className="term-notice">
                Event: {legacy.event_name ?? "Unknown"} · Variant: {legacy.model_variant ?? "baseline"} ·
                Source: {legacy.generated_from ?? "legacy_baseline_model"}
              </div>
              {diagnosticsErrors.length > 0 ? (
                <div className="term-notice" role="alert">
                  {diagnosticsErrors.join(" ")}
                </div>
              ) : null}

              <section className="research-section">
                <h2 className="research-section-heading">Top legacy rankings</h2>
                {rankings.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline rankings in this snapshot.</div>
                  </div>
                ) : (
                  <DataTable>
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Player</th>
                        <th className="num">Composite</th>
                        <th className="num">Course</th>
                        <th className="num">Form</th>
                        <th className="num">Momentum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankings.slice(0, 25).map((row) => (
                        <tr key={`${row.player_key ?? row.player}-${row.rank}`}>
                          <td>{row.rank}</td>
                          <td>{row.player}</td>
                          <td className="num metric">{row.composite.toFixed(1)}</td>
                          <td className="num metric">{row.course_fit.toFixed(1)}</td>
                          <td className="num metric">{row.form.toFixed(1)}</td>
                          <td className="num metric">{row.momentum.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </DataTable>
                )}
              </section>

              <section className="research-section">
                <h2 className="research-section-heading">Legacy matchup edges</h2>
                {matchupBets.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline matchup edges in this snapshot.</div>
                  </div>
                ) : (
                  <DataTable>
                    <thead>
                      <tr>
                        <th>Pick</th>
                        <th>Opponent</th>
                        <th>Book</th>
                        <th className="num">Odds</th>
                        <th className="num">Edge</th>
                        <th>Tier</th>
                      </tr>
                    </thead>
                    <tbody>
                      {matchupBets.slice(0, 25).map((bet) => (
                        <tr key={`${bet.pick_key}-${bet.opponent_key}-${bet.book}-${bet.odds}`}>
                          <td>{bet.pick}</td>
                          <td>{bet.opponent}</td>
                          <td>{bet.book ?? "—"}</td>
                          <td className="num metric">{bet.odds}</td>
                          <td className="num metric">{bet.ev_pct ?? "—"}</td>
                          <td>{bet.tier ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </DataTable>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
