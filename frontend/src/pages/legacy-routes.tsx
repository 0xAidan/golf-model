import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, CircleAlert, NotebookPen, Radar, ShieldAlert, TrendingUp, TrendingDown, Minus } from "lucide-react"

import { BarTrendChart } from "@/components/charts"
import { CourseGuide } from "@/components/course-guide"
import { PlayerProfileSections } from "@/components/player-profile-sections"
import { api } from "@/lib/api"
import { eventToCourseKey, COURSE_MAP, ALL_COURSES } from "@/lib/course-data"
import { formatDateTime, formatNumber, formatUnits } from "@/lib/format"
import { mergeTrackRecordEvents, type MergedTrackRecordEvent } from "@/lib/track-record"
import type {
  CompositePlayer,
  DashboardState,
  GradedTournamentSummary,
  PlayerProfile,
  PredictionRunResponse,
} from "@/lib/types"
import {
  TREND_ARROW,
  TREND_COLOR,
} from "@/pages/page-shared"

/* ── Shared mini-components ─────────────────── */
function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{message}</div>
    </div>
  )
}

function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div style={{ marginBottom: 10, display: "flex", alignItems: "baseline", gap: 10 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--text-muted)" }}>
        {title}
      </div>
      {description && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-faint)" }}>{description}</div>
      )}
    </div>
  )
}

/* ── Players page ───────────────────────────── */
export function PlayersPage({
  players,
  selectedPlayerProfile,
  onPlayerSelect,
  richProfilesEnabled,
}: {
  players: CompositePlayer[]
  selectedPlayerProfile?: PlayerProfile
  onPlayerSelect: (playerKey: string) => void
  richProfilesEnabled: boolean
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const handleToggle = (playerKey: string) => {
    if (expandedKey === playerKey) {
      setExpandedKey(null)
      onPlayerSelect("")
      return
    }
    setExpandedKey(playerKey)
    onPlayerSelect(playerKey)
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
      <PageHeader title="Player Rankings" description="Full model board — click any row to expand the player's full projection profile." />
      <div className="card">
        {players.length > 0 ? (
          <div style={{ overflow: "hidden" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th>Player</th>
                  <th className="right">Composite</th>
                  <th className="right">Course</th>
                  <th className="right">Form</th>
                  <th className="right">Momentum</th>
                  <th className="center">Trend</th>
                </tr>
              </thead>
              <tbody>
                {players.map((player) => {
                  const isExpanded = player.player_key === expandedKey
                  const dir = player.momentum_direction ?? ""
                  const arrow = TREND_ARROW[dir] ?? "—"
                  const trendColor = TREND_COLOR[dir] ?? "var(--text-faint)"
                  const profileReady =
                    isExpanded &&
                    Boolean(selectedPlayerProfile) &&
                    selectedPlayerProfile?.player_key === player.player_key

                  return (
                    <>
                      <tr
                        key={player.player_key}
                        onClick={() => handleToggle(player.player_key)}
                        style={{ cursor: "pointer" }}
                        data-testid={`player-row-${player.player_key}`}
                      >
                        <td className="rank-cell">{player.rank}</td>
                        <td className="player-name">
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ fontWeight: 600, color: "var(--text)" }}>{player.player_display}</span>
                            <ChevronDown
                              size={13}
                              style={{
                                color: "var(--text-faint)",
                                transform: isExpanded ? "rotate(180deg)" : "none",
                                transition: "transform 180ms ease",
                                flexShrink: 0,
                              }}
                            />
                          </div>
                        </td>
                        <td className="right num" style={{ fontWeight: 700, color: "var(--cyan)" }}>
                          {formatNumber(player.composite, 1)}
                        </td>
                        <td className="right num" style={{ color: "var(--text-muted)" }}>
                          {formatNumber(player.course_fit, 1)}
                        </td>
                        <td className="right num" style={{ color: "var(--text-muted)" }}>
                          {formatNumber(player.form, 1)}
                        </td>
                        <td className="right num" style={{ color: "var(--text-muted)" }}>
                          {formatNumber(player.momentum, 1)}
                        </td>
                        <td className="center">
                          <span style={{ color: trendColor, fontSize: 14, fontWeight: 700 }}>{arrow}</span>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${player.player_key}-detail`}>
                          <td colSpan={7} style={{ padding: 0 }}>
                            <div
                              style={{
                                background: "var(--bg-2)",
                                borderTop: "1px solid var(--divider)",
                                padding: 16,
                              }}
                            >
                              {richProfilesEnabled ? (
                                <PlayerProfileSections
                                  player={player}
                                  profile={selectedPlayerProfile}
                                  profileReady={profileReady}
                                />
                              ) : (
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                                  {[
                                    { label: "Composite", value: formatNumber(player.composite, 1) },
                                    { label: "Course fit", value: formatNumber(player.course_fit, 1) },
                                    { label: "Form", value: formatNumber(player.form, 1) },
                                    { label: "Momentum", value: formatNumber(player.momentum, 1) },
                                  ].map(({ label, value }) => (
                                    <div key={label} className="kpi-tile neutral">
                                      <div className="kpi-label">{label}</div>
                                      <div className="kpi-value num" style={{ fontSize: 18 }}>{value}</div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="card-body">
            <EmptyState message="No players available yet for this event context." />
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Course page ────────────────────────────── */
export function CoursePage({
  dashboard,
  players,
  predictionRun,
}: {
  dashboard?: DashboardState
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
}) {
  const topPlayers = players.slice(0, 10)

  // Resolve the active course from the event name, fall back to Augusta
  const courseKey = eventToCourseKey(predictionRun?.event_name)
  const activeCourse = (courseKey ? COURSE_MAP[courseKey] : null) ?? ALL_COURSES[0]

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <PageHeader title="Course Profile" description="Event and field quality diagnostics." />

      {/* KPI strip */}
      <div className="kpi-grid">
        <div className="kpi-tile green">
          <div className="kpi-label">Event</div>
          <div className="kpi-value" style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
            {predictionRun?.event_name ?? "—"}
          </div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Course</div>
          <div className="kpi-value" style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
            {predictionRun?.course_name ?? "—"}
          </div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Cross-tour backfill</div>
          <div
            className="kpi-value"
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: predictionRun?.field_validation?.cross_tour_backfill_used
                ? "var(--warning)"
                : "var(--text)",
            }}
          >
            {predictionRun?.field_validation?.cross_tour_backfill_used ? "Active" : "Standard"}
          </div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Last graded</div>
          <div className="kpi-value" style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
            {dashboard?.latest_graded_tournament?.name ?? "—"}
          </div>
        </div>
      </div>

      {/* Hole-by-hole course guide */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">Hole-by-Hole Guide</div>
          <div className="card-desc">{activeCourse.name} · {activeCourse.location}</div>
        </div>
        <div className="card-body">
          <CourseGuide course={activeCourse} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
        {/* Field-fit chart */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Field-fit distribution</div>
            <div className="card-desc">Top players by composite score</div>
          </div>
          <div className="card-body">
            {topPlayers.length > 0 ? (
              <BarTrendChart
                labels={topPlayers.map((p) => p.player_display.split(" ").pop() ?? p.player_display)}
                values={topPlayers.map((p) => p.composite)}
                color="#22c55e"
              />
            ) : (
              <EmptyState message="Run a prediction to populate field-fit distributions." />
            )}
          </div>
        </div>

        {/* Course risk notes */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Risk notes</div>
          </div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              {
                label: "Major event",
                value: predictionRun?.field_validation?.major_event ? "Yes — cross-tour coverage active" : "No",
                icon: Radar,
                warn: predictionRun?.field_validation?.major_event,
              },
              {
                label: "Thin-round players",
                value: String(predictionRun?.field_validation?.players_with_thin_rounds?.length ?? 0),
                icon: ShieldAlert,
                warn: (predictionRun?.field_validation?.players_with_thin_rounds?.length ?? 0) > 0,
              },
              {
                label: "Missing DG skill",
                value: String(predictionRun?.field_validation?.players_missing_dg_skill?.length ?? 0),
                icon: CircleAlert,
                warn: (predictionRun?.field_validation?.players_missing_dg_skill?.length ?? 0) > 0,
              },
              {
                label: "Prediction artifact",
                value: dashboard?.latest_prediction_artifact?.path ?? "—",
                icon: NotebookPen,
                warn: false,
              },
            ].map(({ label, value, icon: Icon, warn }) => (
              <div
                key={label}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  padding: "10px 12px",
                  background: "var(--surface-2)",
                  border: `1px solid ${warn ? "rgba(245,158,11,0.2)" : "var(--border)"}`,
                  borderRadius: "var(--r-md)",
                }}
              >
                <Icon
                  size={14}
                  style={{
                    color: warn ? "var(--warning)" : "var(--text-faint)",
                    marginTop: 1,
                    flexShrink: 0,
                  }}
                />
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-faint)", marginBottom: 2 }}>
                    {label}
                  </div>
                  <div style={{ fontSize: 12, color: warn ? "var(--warning)" : "var(--text)", fontWeight: 500 }}>
                    {value}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Grading page ───────────────────────────── */
export function GradingPage({ gradingHistory }: { gradingHistory: GradedTournamentSummary[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const labels = gradingHistory
    .slice(0, 8)
    .reverse()
    .map((item) => item.name.replace(/open|championship|invitational/gi, "").trim().split(" ").slice(-1)[0] ?? item.name)
  const profits = gradingHistory
    .slice(0, 8)
    .reverse()
    .map((item) => Number(item.total_profit ?? 0))

  const totalProfit = gradingHistory.reduce((s, t) => s + Number(t.total_profit ?? 0), 0)
  const totalHits = gradingHistory.reduce((s, t) => s + (t.hits ?? 0), 0)
  const totalPicks = gradingHistory.reduce((s, t) => s + (t.graded_pick_count ?? 0), 0)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <PageHeader title="Grading History" description="Tournament-by-tournament performance tracking." />

      {/* KPI strip */}
      <div className="kpi-grid">
        <div className="kpi-tile green">
          <div className="kpi-label">Total P&L</div>
          <div className={`kpi-value num ${totalProfit >= 0 ? "green" : ""}`}>{formatUnits(totalProfit)}</div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Tournaments</div>
          <div className="kpi-value num">{gradingHistory.length}</div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Hit rate</div>
          <div className="kpi-value num">
            {totalPicks > 0 ? `${((totalHits / totalPicks) * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="kpi-detail">{totalHits}/{totalPicks} picks</div>
        </div>
        <div className="kpi-tile gold">
          <div className="kpi-label">Latest event</div>
          <div className="kpi-value" style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
            {gradingHistory[0]?.name ?? "—"}
          </div>
          <div className="kpi-detail">{formatDateTime(gradingHistory[0]?.last_graded_at)}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 16 }}>
        {/* Season trend */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Season P&L trend</div>
          </div>
          <div className="card-body">
            {profits.length > 0 ? (
              <BarTrendChart labels={labels} values={profits} color="#22C55E" />
            ) : (
              <EmptyState message="Grade a tournament to start the season trend view." />
            )}
          </div>
        </div>

        {/* Event list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {gradingHistory.map((item) => {
            const id = `${item.event_id}-${item.year}`
            const isExpanded = expandedId === id
            const profit = Number(item.total_profit ?? 0)
            const picks = item.graded_pick_count ?? 0
            const hits = item.hits ?? 0
            const hr = picks > 0 ? `${((hits / picks) * 100).toFixed(0)}%` : "—"

            return (
              <div key={id} className="tr-event">
                <div
                  className="tr-event-header"
                  onClick={() => setExpandedId(isExpanded ? null : id)}
                  data-testid={`grading-event-${id}`}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="tr-event-name">{item.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 2 }}>
                      {hits}/{picks} hits · {hr}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: 700,
                        fontVariantNumeric: "tabular-nums",
                        color: profit >= 0 ? "var(--positive)" : "var(--danger)",
                      }}
                    >
                      {formatUnits(profit)}
                    </span>
                    <ChevronDown
                      size={13}
                      style={{
                        color: "var(--text-faint)",
                        transform: isExpanded ? "rotate(180deg)" : "none",
                        transition: "transform 180ms ease",
                        flexShrink: 0,
                      }}
                    />
                  </div>
                </div>
                {isExpanded && (
                  <div className="tr-event-body">
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <div className="kpi-tile neutral">
                        <div className="kpi-label">Course</div>
                        <div className="kpi-value" style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>
                          {item.course ?? "—"}
                        </div>
                      </div>
                      <div className="kpi-tile neutral">
                        <div className="kpi-label">Year</div>
                        <div className="kpi-value num" style={{ fontSize: 16 }}>{item.year ?? "—"}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          {gradingHistory.length === 0 && (
            <div className="card">
              <div className="card-body">
                <EmptyState message="No graded events yet." />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Track Record page ──────────────────────── */
export function TrackRecordPage() {
  const trackRecordQuery = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
  })

  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const mergedResult = mergeTrackRecordEvents(trackRecordQuery.data?.events ?? [])
  // mergeTrackRecordEvents returns { events, totals } — never a plain array
  const events: MergedTrackRecordEvent[] = Array.isArray(mergedResult)
    ? (mergedResult as MergedTrackRecordEvent[])
    : ((mergedResult as { events: MergedTrackRecordEvent[] }).events ?? [])

  // MergedTrackRecordEvent fields: name, course, wins, losses, pushes, profit, picks[]
  const totalProfit = events.reduce((s, e) => s + Number(e.profit ?? 0), 0)
  const totalWins   = events.reduce((s, e) => s + (e.wins ?? 0), 0)
  const totalPicks  = events.reduce((s, e) => s + (e.wins ?? 0) + (e.losses ?? 0) + (e.pushes ?? 0), 0)

  if (trackRecordQuery.isLoading) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: "var(--text-faint)", fontSize: 13 }}>
        Loading track record…
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <PageHeader title="Track Record" description="Full historical model performance across all graded tournaments." />

      {/* Summary strip */}
      <div className="kpi-grid">
        <div className={`kpi-tile ${totalProfit >= 0 ? "green" : "neutral"}`}>
          <div className="kpi-label">Total P&L</div>
          <div className={`kpi-value num ${totalProfit >= 0 ? "green" : ""}`}>{formatUnits(totalProfit)}</div>
          <div className="kpi-detail">all tournaments</div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Tournaments</div>
          <div className="kpi-value num">{events.length}</div>
        </div>
        <div className="kpi-tile neutral">
          <div className="kpi-label">Win rate</div>
          <div className="kpi-value num">
            {totalPicks > 0 ? `${((totalWins / totalPicks) * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="kpi-detail">{totalWins}/{totalPicks} picks</div>
        </div>
        <div className="kpi-tile gold">
          <div className="kpi-label">Wins</div>
          <div className="kpi-value num gold">{totalWins}</div>
          <div className="kpi-detail">outright picks won</div>
        </div>
      </div>

      {/* Event accordion */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {events.length > 0 ? (
          events.map((event, idx) => {
            // Use index as key — MergedTrackRecordEvent has no id field
            const isExpanded = expandedIdx === idx
            const profit = Number(event.profit ?? 0)
            const picks = event.picks ?? []
            const eventTotal = (event.wins ?? 0) + (event.losses ?? 0) + (event.pushes ?? 0)
            const hr = eventTotal > 0
              ? `${(((event.wins ?? 0) / eventTotal) * 100).toFixed(0)}%`
              : "—"

            return (
              <div key={`${event.name}-${idx}`} className="tr-event">
                <div
                  className="tr-event-header"
                  onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  data-testid={`track-record-event-${idx}`}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="tr-event-name">{event.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 2 }}>
                      {event.wins ?? 0}W / {event.losses ?? 0}L / {event.pushes ?? 0}P · {hr}{event.course ? ` · ${event.course}` : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: 700,
                        fontVariantNumeric: "tabular-nums",
                        color: profit >= 0 ? "var(--positive)" : "var(--danger)",
                      }}
                    >
                      {formatUnits(profit)}
                    </span>
                    <ChevronDown
                      size={13}
                      style={{
                        color: "var(--text-faint)",
                        transform: isExpanded ? "rotate(180deg)" : "none",
                        transition: "transform 180ms ease",
                        flexShrink: 0,
                      }}
                    />
                  </div>
                </div>

                {isExpanded && picks.length > 0 && (
                  <div className="tr-event-body">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Pick</th>
                          <th>Opponent</th>
                          <th>Odds</th>
                          <th className="center">Result</th>
                          <th className="right">P&L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {picks.map((pick, i) => {
                          // StaticTrackRecordPick fields: pick, opponent, odds, result, pl
                          const isWin = pick.result?.toLowerCase() === "win"
                          const isLoss = pick.result?.toLowerCase() === "loss"
                          return (
                            <tr key={i} data-testid={`pick-row-${i}`}>
                              <td style={{ fontWeight: 600, color: "var(--text)" }}>{pick.pick}</td>
                              <td style={{ color: "var(--text-muted)", fontSize: 12 }}>{pick.opponent}</td>
                              <td style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>{pick.odds}</td>
                              <td className="center">
                                {isWin ? (
                                  <TrendingUp size={14} style={{ color: "var(--positive)", margin: "0 auto" }} />
                                ) : isLoss ? (
                                  <TrendingDown size={14} style={{ color: "var(--danger)", margin: "0 auto" }} />
                                ) : (
                                  <Minus size={14} style={{ color: "var(--text-faint)", margin: "0 auto" }} />
                                )}
                              </td>
                              <td
                                className="right num"
                                style={{
                                  fontWeight: 700,
                                  color:
                                    Number(pick.pl) > 0
                                      ? "var(--positive)"
                                      : Number(pick.pl) < 0
                                      ? "var(--danger)"
                                      : "var(--text-muted)",
                                }}
                              >
                                {formatUnits(pick.pl)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {isExpanded && picks.length === 0 && (
                  <div className="tr-event-body">
                    <EmptyState message="No pick detail available for this tournament." />
                  </div>
                )}
              </div>
            )
          })
        ) : (
          <div className="card">
            <div className="card-body">
              <EmptyState message="No track record data yet. Grade tournaments to build your history." />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
