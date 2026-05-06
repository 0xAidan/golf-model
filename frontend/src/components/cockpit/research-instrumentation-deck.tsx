import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { api } from "@/lib/api"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import type { LiveRefreshSnapshot } from "@/lib/types"

function resolveLabEventId(snapshot: LiveRefreshSnapshot | null, tab: PredictionTab): string | null {
  if (tab === "live") {
    const id = snapshot?.live_tournament?.source_event_id?.trim()
    return id || null
  }
  if (tab === "upcoming") {
    const id = snapshot?.upcoming_tournament?.source_event_id?.trim()
    return id || null
  }
  return null
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="term-notice" style={{ marginTop: 8 }}>
      {message}{" "}
      <a href="/docs" target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>
        Open API docs
      </a>{" "}
      to verify the backend, then retry.
    </div>
  )
}

export function ResearchInstrumentationDeck({
  liveSnapshot,
  predictionTab,
  hideTitle = false,
}: {
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
  /** When wrapped (e.g. lab cockpit collapsible), omit the section heading */
  hideTitle?: boolean
}) {
  const eventId = resolveLabEventId(liveSnapshot, predictionTab)

  const activeSection =
    predictionTab === "live"
      ? liveSnapshot?.live_tournament
      : predictionTab === "upcoming"
        ? liveSnapshot?.upcoming_tournament
        : null
  const shadowRows = activeSection?.diagnostics?.shadow_mc_rows_written

  const calibrationQuery = useQuery({
    queryKey: ["lab", "calibration-by-market"],
    queryFn: api.getCalibrationByMarket,
    staleTime: 60_000,
  })

  const clvQuery = useQuery({
    queryKey: ["lab", "clv-summary"],
    queryFn: api.getClvSummary,
    staleTime: 60_000,
  })

  const abQuery = useQuery({
    queryKey: ["lab", "ab-report", eventId],
    queryFn: () => api.getResearchAbReport(eventId as string, { persist: false }),
    enabled: Boolean(eventId),
    staleTime: 30_000,
  })

  const [abTableExpanded, setAbTableExpanded] = useState(false)

  return (
    <div
      className="research-instrumentation-deck"
      style={{
        flexShrink: 0,
        padding: "12px 12px 24px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
        maxWidth: "min(100%, 720px)",
        margin: "0 auto",
        width: "100%",
        fontSize: 12,
      }}
    >
      {!hideTitle ? (
        <h2 style={{ fontSize: 14, fontWeight: 600, margin: 0, color: "var(--text-muted)" }}>
          Research instrumentation
        </h2>
      ) : null}

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Calibration (by market)</div>
            <div className="card-desc">Empirical buckets from calibration_curve per bet_type.</div>
          </div>
        </div>
        <div className="card-body">
          {calibrationQuery.isError ? (
            <ErrorPanel message={(calibrationQuery.error as Error)?.message ?? "Request failed."} />
          ) : calibrationQuery.isLoading ? (
            <div className="empty-state-title">Loading…</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {(calibrationQuery.data?.bet_types ?? []).map((betType) => {
                const rows = calibrationQuery.data?.curves[betType] ?? []
                const label = betType === "" ? "(global)" : betType
                return (
                  <div key={betType || "__global__"}>
                    <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>{label}</div>
                    {rows.length === 0 ? (
                      <div className="empty-state-title">No rows.</div>
                    ) : (
                      <div className="research-instrumentation-table-wrap">
                        <table className="data-table research-instrumentation-data-table">
                          <thead>
                            <tr>
                              <th>Bucket</th>
                              <th>Predicted avg</th>
                              <th>Actual rate</th>
                              <th>N</th>
                              <th>Correction</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((r) => (
                              <tr key={`${betType}-${r.probability_bucket}`}>
                                <td>{r.probability_bucket}</td>
                                <td>{r.predicted_avg != null ? r.predicted_avg.toFixed(4) : "—"}</td>
                                <td>{r.actual_hit_rate != null ? r.actual_hit_rate.toFixed(4) : "—"}</td>
                                <td>{r.sample_size}</td>
                                <td>{r.correction_factor != null ? r.correction_factor.toFixed(4) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">CLV by book</div>
            <div className="card-desc">Aggregates from clv_log (feature flag clv_tracking).</div>
          </div>
        </div>
        <div className="card-body">
          {clvQuery.isError ? (
            <ErrorPanel message={(clvQuery.error as Error)?.message ?? "Request failed."} />
          ) : clvQuery.isLoading ? (
            <div className="empty-state-title">Loading…</div>
          ) : (
            <>
              <div style={{ fontSize: 12, marginBottom: 10 }}>
                Overall:{" "}
                <strong>{clvQuery.data?.overall.n_bets ?? 0}</strong> bets
                {clvQuery.data?.overall.avg_clv_pct != null
                  ? ` · avg CLV ${clvQuery.data.overall.avg_clv_pct}%`
                  : ""}{" "}
                {clvQuery.data?.overall.significant ? (
                  <span style={{ color: "var(--accent-green)" }}>(significant)</span>
                ) : (
                  <span style={{ color: "var(--text-faint)" }}>(below min for significance)</span>
                )}
              </div>
              <div className="research-instrumentation-table-wrap">
                <table className="data-table research-instrumentation-data-table">
                  <thead>
                    <tr>
                      <th>Book</th>
                      <th>N</th>
                      <th>Avg CLV %</th>
                      <th>Sig.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(clvQuery.data?.by_book ?? []).map((row) => (
                      <tr key={row.market_book}>
                        <td>{row.market_book}</td>
                        <td>{row.n_bets}</td>
                        <td>{row.avg_clv_pct != null ? row.avg_clv_pct : "—"}</td>
                        <td>{row.significant ? "yes" : "no"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">AB report (v5 vs legacy)</div>
            <div className="card-desc">
              Stored rows: <strong>live/upcoming (v5)</strong> vs <strong>legacy</strong> — not Lab{" "}
              <code style={{ fontSize: 10 }}>lab_*</code> sections.
            </div>
          </div>
        </div>
        <div className="card-body">
          {!eventId ? (
            <div className="term-notice">
              No <code>source_event_id</code> on the current snapshot for this tab. Switch to{" "}
              <strong>Live</strong> or <strong>Upcoming</strong> so the snapshot includes an event id, then return
              here.
            </div>
          ) : abQuery.isError ? (
            <ErrorPanel message={(abQuery.error as Error)?.message ?? "Request failed."} />
          ) : abQuery.isLoading ? (
            <div className="empty-state-title">Loading AB report…</div>
          ) : abQuery.data && !abQuery.data.ok ? (
            <div className="term-notice">{abQuery.data.error ?? "Report unavailable."}</div>
          ) : (
            <>
              <div style={{ fontSize: 12, marginBottom: 8 }}>
                Event <code>{eventId}</code> · paired keys:{" "}
                <strong>{abQuery.data?.counts?.paired_keys ?? 0}</strong> · raw rows:{" "}
                {abQuery.data?.counts?.raw_rows ?? 0}
              </div>
              <div style={{ fontSize: 12, marginBottom: 8 }}>
                Mean Δ model_prob (v5 − legacy):{" "}
                <strong>{abQuery.data?.paired_metrics?.mean_model_prob_delta_v5_minus_legacy ?? "—"}</strong> · Mean Δ
                ev: <strong>{abQuery.data?.paired_metrics?.mean_ev_delta_v5_minus_legacy ?? "—"}</strong>
              </div>
              {abQuery.data?.truncated_paired_samples ? (
                <div className="term-notice" style={{ marginBottom: 8 }}>
                  Sample table truncated (first 200 pairs).
                </div>
              ) : null}
              <p style={{ fontSize: 11, marginBottom: 10, lineHeight: 1.5, color: "var(--text-muted)" }}>
                This report pairs <strong>production snapshot</strong> rows — use it for calibration research, not as a
                diff vs the <strong>Lab Cockpit</strong> center board (Lab uses <code style={{ fontSize: 10 }}>lab_*</code>{" "}
                recomputation).
              </p>
              <div className="research-instrumentation-table-wrap">
                <table className="data-table research-instrumentation-data-table research-instrumentation-ab-table">
                  <thead>
                    <tr>
                      <th>Market</th>
                      <th>Pick</th>
                      <th>Book</th>
                      <th>v5 p</th>
                      <th>Legacy p</th>
                      <th>v5 EV</th>
                      <th>Legacy EV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(abQuery.data?.paired_samples ?? [])
                      .slice(0, abTableExpanded ? 50 : 10)
                      .map((s, i) => (
                      <tr key={i}>
                        <td>
                          {s.key.market_family}/{s.key.market_type}
                        </td>
                        <td className="research-instrumentation-pick-cell">
                          {s.key.player_key} vs {s.key.opponent_key}
                        </td>
                        <td>{s.key.book}</td>
                        <td>{s.v5_model_prob != null ? s.v5_model_prob.toFixed(3) : "—"}</td>
                        <td>{s.legacy_model_prob != null ? s.legacy_model_prob.toFixed(3) : "—"}</td>
                        <td>{s.v5_ev != null ? s.v5_ev.toFixed(3) : "—"}</td>
                        <td>{s.legacy_ev != null ? s.legacy_ev.toFixed(3) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(abQuery.data?.paired_samples?.length ?? 0) > 10 ? (
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ marginTop: 8, fontSize: 11 }}
                  onClick={() => setAbTableExpanded((v) => !v)}
                >
                  {abTableExpanded ? "Show fewer rows" : `Show more sample rows (${Math.min(50, abQuery.data?.paired_samples?.length ?? 0)} max)`}
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Shadow Monte Carlo / flags</div>
            <div className="card-desc">Read-only hints from snapshot diagnostics (no EV wiring).</div>
          </div>
        </div>
        <div className="card-body" style={{ fontSize: 12, lineHeight: 1.5 }}>
          {predictionTab === "past" ? (
            <div className="term-notice">Shadow row counts are attached to live/upcoming tournament sections.</div>
          ) : shadowRows != null && shadowRows > 0 ? (
            <p style={{ margin: 0 }}>
              This tick wrote <strong>{shadowRows}</strong> shadow row(s) (<code>diagnostics.shadow_mc_rows_written</code>
              ).
            </p>
          ) : (
            <p style={{ margin: 0 }}>
              No shadow rows recorded on this section for the latest snapshot (or count is zero). Enable{" "}
              <code>shadow_monte_carlo_v1</code> / <code>shadow_monte_carlo_v2</code> (or env equivalents documented in
              AGENTS_KNOWLEDGE) on the server to append diagnostics-only simulations.
            </p>
          )}
        </div>
      </div>

      <div style={{ fontSize: 11, color: "var(--text-faint)" }}>
        Diagnostics UI: <Link to="/research/diagnostics">/research/diagnostics</Link>
      </div>
    </div>
  )
}
