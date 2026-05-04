import { Link } from "react-router-dom"

import type { LiveRefreshSnapshot } from "@/lib/types"

export function LegacyModelPage({ liveSnapshot }: { liveSnapshot: LiveRefreshSnapshot | null }) {
  const legacy = liveSnapshot?.legacy_tournament
  const rankings = legacy?.rankings ?? []
  const matchupBets = legacy?.matchup_bets_all_books ?? legacy?.matchup_bets ?? []
  const diagnosticsErrors = legacy?.diagnostics?.errors ?? []

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 12px" }}>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Legacy Model (Baseline)</div>
            <div className="card-desc">
              Read-only fallback lane for last month&apos;s baseline model.
            </div>
          </div>
          <Link to="/" className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }}>
            Back to cockpit
          </Link>
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {!legacy ? (
            <div className="term-notice">
              Legacy baseline snapshot is not available yet. Refresh the live snapshot and try again.
            </div>
          ) : (
            <>
              <div className="term-notice">
                Event: {legacy.event_name ?? "Unknown"} • Variant: {legacy.model_variant ?? "baseline"} • Source:{" "}
                {legacy.generated_from ?? "legacy_baseline_model"}
              </div>
              {diagnosticsErrors.length > 0 ? (
                <div className="term-notice">
                  {diagnosticsErrors.join(" ")}
                </div>
              ) : null}

              <section>
                <div className="section-title" style={{ marginBottom: 8 }}>
                  Top Legacy Rankings
                </div>
                {rankings.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline rankings captured in this snapshot.</div>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Player</th>
                          <th>Composite</th>
                          <th>Course</th>
                          <th>Form</th>
                          <th>Momentum</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rankings.slice(0, 25).map((row) => (
                          <tr key={`${row.player_key ?? row.player}-${row.rank}`}>
                            <td>{row.rank}</td>
                            <td>{row.player}</td>
                            <td>{row.composite.toFixed(1)}</td>
                            <td>{row.course_fit.toFixed(1)}</td>
                            <td>{row.form.toFixed(1)}</td>
                            <td>{row.momentum.toFixed(1)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section>
                <div className="section-title" style={{ marginBottom: 8 }}>
                  Legacy Matchup Edges
                </div>
                {matchupBets.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-title">No baseline matchup edges available in this snapshot.</div>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Pick</th>
                          <th>Opponent</th>
                          <th>Book</th>
                          <th>Odds</th>
                          <th>Edge</th>
                          <th>Tier</th>
                        </tr>
                      </thead>
                      <tbody>
                        {matchupBets.slice(0, 25).map((bet) => (
                          <tr key={`${bet.pick_key}-${bet.opponent_key}-${bet.book}-${bet.odds}`}>
                            <td>{bet.pick}</td>
                            <td>{bet.opponent}</td>
                            <td>{bet.book ?? "--"}</td>
                            <td>{bet.odds}</td>
                            <td>{bet.ev_pct ?? "--"}</td>
                            <td>{bet.tier ?? "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
