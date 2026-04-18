import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, CircleAlert, NotebookPen, Radar, ShieldAlert } from "lucide-react"

import { BarTrendChart } from "@/components/charts"
import { PlayerProfileSections } from "@/components/player-profile-sections"
import { MetricTile, SectionTitle, SurfaceCard } from "@/components/shell"
import { api } from "@/lib/api"
import { formatDateTime, formatNumber, formatUnits } from "@/lib/format"
import { mergeTrackRecordEvents } from "@/lib/track-record"
import type {
  CompositePlayer,
  DashboardState,
  GradedTournamentSummary,
  MatchupBet,
  PlayerProfile,
  PredictionRunResponse,
} from "@/lib/types"
import {
  EmptyState,
  InfoRow,
  TREND_ARROW,
  TREND_COLOR,
  buildMatchupKey,
  getTierStyle,
} from "@/pages/page-shared"

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
    <SurfaceCard>
      <SectionTitle title="Model Rankings" description="Click any player row to expand their full projection profile." />
      {players.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm" role="grid">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                <th className="px-3 py-3 font-medium">Rank</th>
                <th className="px-3 py-3 font-medium">Player</th>
                <th className="px-3 py-3 font-medium text-right">Composite</th>
                <th className="px-3 py-3 font-medium text-right">Course Fit</th>
                <th className="px-3 py-3 font-medium text-right">Form</th>
                <th className="px-3 py-3 font-medium text-right">Momentum</th>
                <th className="px-3 py-3 font-medium text-center">Trend</th>
              </tr>
            </thead>
            <tbody>
              {players.map((player) => {
                const isExpanded = player.player_key === expandedKey
                const dir = player.momentum_direction ?? ""
                const arrow = TREND_ARROW[dir] ?? "—"
                const trendColor = TREND_COLOR[dir] ?? "text-slate-500"
                const profileReady =
                  isExpanded &&
                  Boolean(selectedPlayerProfile) &&
                  selectedPlayerProfile?.player_key === player.player_key

                return (
                  <tr key={player.player_key} className="group">
                    <td colSpan={7} className="p-0">
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        aria-label={`${player.player_display} ranked ${player.rank}`}
                        tabIndex={0}
                        className={`flex w-full cursor-pointer items-center transition hover:bg-white/5 ${isExpanded ? "bg-white/3" : ""}`}
                        onClick={() => handleToggle(player.player_key)}
                      >
                        <span className="w-[calc(100%/7)] px-3 py-3 text-left text-slate-400">{player.rank}</span>
                        <span className="flex w-[calc(100%/7)] items-center gap-2 px-3 py-3 text-left font-medium text-white">
                          {player.player_display}
                          <ChevronDown className={`h-3.5 w-3.5 text-slate-500 transition ${isExpanded ? "rotate-180" : ""}`} />
                        </span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.course_fit, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.form, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.momentum, 1)}</span>
                        <span className={`w-[calc(100%/7)] px-3 py-3 text-center text-lg ${trendColor}`}>{arrow}</span>
                      </button>
                      {isExpanded ? (
                        <div className="border-t border-white/8 bg-white/3 px-4 py-5">
                          {richProfilesEnabled ? (
                            <PlayerProfileSections
                              player={player}
                              profile={selectedPlayerProfile}
                              profileReady={profileReady}
                            />
                          ) : (
                            <div className="space-y-4">
                              <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                                Rich profile sections are currently disabled by configuration.
                              </div>
                              <div className="grid gap-4 md:grid-cols-4">
                                <MetricTile label="Composite" value={formatNumber(player.composite, 1)} />
                                <MetricTile label="Course fit" value={formatNumber(player.course_fit, 1)} />
                                <MetricTile label="Form" value={formatNumber(player.form, 1)} />
                                <MetricTile label="Momentum" value={formatNumber(player.momentum, 1)} />
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message="No players available yet for this event context." />
      )}
    </SurfaceCard>
  )
}

export function MatchupsPage({
  matchups,
  emptyMessage,
}: {
  matchups: MatchupBet[]
  emptyMessage: string
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const handleToggle = (key: string) => {
    setExpandedKey(expandedKey === key ? null : key)
  }

  return (
    <SurfaceCard>
      <SectionTitle title="Matchup conviction map" description="Scan tier, edge, pricing, and momentum at a glance. Click any row to expand." />
      {matchups.length ? (
        <div className="space-y-3">
          {matchups.map((matchup) => {
            const key = buildMatchupKey(matchup)
            const isExpanded = expandedKey === key
            return (
              <div key={key} className="rounded-2xl border border-white/8 bg-black/20 transition">
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  aria-label={`${matchup.pick} vs ${matchup.opponent}`}
                  tabIndex={0}
                  className={`flex w-full cursor-pointer items-center justify-between gap-4 p-4 text-left transition hover:bg-white/5 ${isExpanded ? "bg-white/3" : ""}`}
                  onClick={() => handleToggle(key)}
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="min-w-0">
                      <p className="font-medium text-white">{matchup.pick}</p>
                      <p className="text-xs text-slate-500">vs {matchup.opponent}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="hidden text-right sm:block">
                      <p className="text-xs text-slate-500">Edge</p>
                      <p className="text-sm font-semibold text-cyan-200">{matchup.ev_pct}</p>
                    </div>
                    <div className="hidden text-right sm:block">
                      <p className="text-xs text-slate-500">Price</p>
                      <p className="text-sm font-semibold text-white">{matchup.odds}</p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${getTierStyle(matchup.tier)}`}>
                      {matchup.tier ?? "lean"}
                    </span>
                    <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isExpanded ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isExpanded ? (
                  <div className="border-t border-white/8 bg-white/3 px-4 py-5">
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-4">
                        <MetricTile label="Edge" value={matchup.ev_pct} />
                        <MetricTile label="Model prob" value={`${(matchup.model_win_prob * 100).toFixed(1)}%`} />
                        <MetricTile label="Implied prob" value={`${(matchup.implied_prob * 100).toFixed(1)}%`} />
                        <MetricTile label="Conviction" value={formatNumber(matchup.conviction, 0)} />
                      </div>
                      <div className="grid gap-4 md:grid-cols-4">
                        <MetricTile label="Composite gap" value={formatNumber(matchup.composite_gap, 1)} />
                        <MetricTile label="Form gap" value={formatNumber(matchup.form_gap, 1)} />
                        <MetricTile label="Course fit gap" value={formatNumber(matchup.course_fit_gap, 1)} />
                        <MetricTile label="Momentum" value={matchup.momentum_aligned ? "Aligned" : "Mixed"} />
                      </div>
                      <BarTrendChart
                        labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
                        values={[
                          matchup.composite_gap,
                          matchup.form_gap,
                          matchup.course_fit_gap,
                          Number(matchup.pick_momentum ?? 0) - Number(matchup.opp_momentum ?? 0),
                          Number(matchup.conviction ?? 0),
                        ]}
                        color="#38bdf8"
                      />
                      <div className="grid gap-4 md:grid-cols-2">
                        <MetricTile label="Book" value={matchup.book ?? "--"} />
                        <MetricTile label="Price" value={matchup.odds} />
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState message={emptyMessage} />
      )}
    </SurfaceCard>
  )
}

export function CoursePage({
  dashboard,
  players,
  predictionRun,
}: {
  dashboard?: DashboardState
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
}) {
  const topPlayers = players.slice(0, 8)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Event" value={predictionRun?.event_name ?? "--"} />
        <MetricTile label="Course" value={predictionRun?.course_name ?? "--"} />
        <MetricTile label="Cross-tour backfill" value={predictionRun?.field_validation?.cross_tour_backfill_used ? "Enabled" : "Standard"} />
        <MetricTile label="Latest graded" value={dashboard?.latest_graded_tournament?.name ?? "--"} />
      </div>
      <div className="grid gap-6 2xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard>
          <SectionTitle title="Field-fit distribution" description="Top of the board by composite score, framed as a course-fit command surface." />
          {topPlayers.length ? (
            <BarTrendChart labels={topPlayers.map((player) => player.player_display.split(" ")[0])} values={topPlayers.map((player) => player.composite)} color="#38bdf8" />
          ) : (
            <EmptyState message="Run a prediction to populate field-fit distributions." />
          )}
        </SurfaceCard>
        <SurfaceCard>
          <SectionTitle title="Course risk notes" description="Macro course context and field quality warnings that matter before a wager goes live." />
          <div className="space-y-3">
            <InfoRow icon={Radar} label="Major event handling" value={predictionRun?.field_validation?.major_event ? "Major-week cross-tour coverage active" : "Standard PGA event"} />
            <InfoRow icon={ShieldAlert} label="Thin-round players" value={String(predictionRun?.field_validation?.players_with_thin_rounds?.length ?? 0)} />
            <InfoRow icon={CircleAlert} label="Missing DG skill" value={String(predictionRun?.field_validation?.players_missing_dg_skill?.length ?? 0)} />
            <InfoRow icon={NotebookPen} label="Prediction artifact" value={dashboard?.latest_prediction_artifact?.path ?? "--"} />
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

export function GradingPage({ gradingHistory }: { gradingHistory: GradedTournamentSummary[] }) {
  const labels = gradingHistory.slice(0, 8).reverse().map((item) => item.name.replace("Open", ""))
  const profits = gradingHistory.slice(0, 8).reverse().map((item) => Number(item.total_profit ?? 0))

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Tournaments graded" value={String(gradingHistory.length)} />
        <MetricTile label="Latest P/L" value={formatUnits(Number(gradingHistory[0]?.total_profit ?? 0))} />
        <MetricTile label="Latest hits" value={String(gradingHistory[0]?.hits ?? 0)} />
        <MetricTile label="Last graded at" value={formatDateTime(gradingHistory[0]?.last_graded_at)} />
      </div>
      <div className="grid gap-6 2xl:grid-cols-[1fr_0.95fr]">
        <SurfaceCard>
          <SectionTitle title="Season trend" description="Durable grading history survives refreshes, restarts, and week-to-week review." />
          {profits.length ? <BarTrendChart labels={labels} values={profits} color="#34d399" /> : <EmptyState message="Grade a tournament to start the season trend view." />}
        </SurfaceCard>
        <SurfaceCard>
          <SectionTitle title="Graded events" description="Tournament-by-tournament status, hit count, and profit." />
          <div className="space-y-3">
            {gradingHistory.map((item) => (
              <div key={`${item.event_id}-${item.year}`} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-white">{item.name}</p>
                    <p className="text-xs text-slate-500">{formatDateTime(item.last_graded_at)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-emerald-300">{formatUnits(Number(item.total_profit ?? 0))}</p>
                    <p className="text-xs text-slate-500">
                      {item.hits ?? 0}/{item.graded_pick_count ?? 0} hits
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function useTrackRecordData() {
  const trackRecordQuery = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
    staleTime: 5 * 60 * 1000,
  })

  return useMemo(() => {
    const apiEvents = trackRecordQuery.data?.events ?? []
    return mergeTrackRecordEvents(apiEvents)
  }, [trackRecordQuery.data])
}

export function TrackRecordPage() {
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  const { events, totals } = useTrackRecordData()
  const totalBets = totals.wins + totals.losses + totals.pushes
  const winRate = totalBets - totals.pushes > 0 ? ((totals.wins / (totalBets - totals.pushes)) * 100).toFixed(1) : "0"
  const roiPct = totalBets > 0 ? ((totals.profit / totalBets) * 100).toFixed(1) : "0"

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-5">
        <MetricTile label="Record" value={`${totals.wins}-${totals.losses}-${totals.pushes}`} />
        <MetricTile label="Win rate" value={`${winRate}%`} tone={Number(winRate) >= 50 ? "positive" : undefined} />
        <MetricTile label="Profit" value={`${totals.profit >= 0 ? "+" : ""}${totals.profit.toFixed(2)}u`} tone={totals.profit >= 0 ? "positive" : "warning"} />
        <MetricTile label="ROI" value={`${Number(roiPct) >= 0 ? "+" : ""}${roiPct}%`} tone={Number(roiPct) >= 0 ? "positive" : "warning"} />
        <MetricTile label="Events" value={String(events.length)} />
      </div>
      <SurfaceCard>
        <SectionTitle title="Event-by-event results" description="2026 PGA Tour season. Matchup-focused betting record." />
        <div className="space-y-2">
          {events.map((event) => {
            const isOpen = expandedEvent === event.name
            const record = `${event.wins}-${event.losses}-${event.pushes}`
            const profitSign = event.profit >= 0 ? "+" : ""
            const profitTone = event.profit >= 0 ? "text-emerald-300" : "text-red-400"

            return (
              <div key={event.name} className="rounded-2xl border border-white/8 bg-black/20">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-label={`${event.name} record ${record}`}
                  tabIndex={0}
                  className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-white/5"
                  onClick={() => setExpandedEvent(isOpen ? null : event.name)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-white">{event.name}</p>
                    <p className="text-xs text-slate-500">{event.course}</p>
                  </div>
                  <div className="flex items-center gap-5">
                    <div className="text-right">
                      <p className="text-sm font-semibold text-white">{record}</p>
                      <p className={`text-xs font-medium ${profitTone}`}>{profitSign}{event.profit.toFixed(2)}u</p>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isOpen ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isOpen ? (
                  <div className="border-t border-white/8 px-5 py-4">
                    {event.picks.length ? (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[480px] text-sm">
                          <thead>
                            <tr className="border-b border-white/10 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                              <th className="px-2 py-2 font-medium">Pick</th>
                              <th className="px-2 py-2 font-medium">vs</th>
                              <th className="px-2 py-2 font-medium text-right">Odds</th>
                              <th className="px-2 py-2 font-medium text-center">Result</th>
                              <th className="px-2 py-2 font-medium text-right">P/L</th>
                            </tr>
                          </thead>
                          <tbody>
                            {event.picks.map((pick, index) => {
                              const resultColor =
                                pick.result === "win" ? "text-emerald-400" : pick.result === "loss" ? "text-red-400" : "text-slate-400"
                              const plColor = pick.pl > 0 ? "text-emerald-300" : pick.pl < 0 ? "text-red-400" : "text-slate-400"
                              return (
                                <tr key={`${pick.pick}-${pick.opponent}-${index}`} className="border-b border-white/5">
                                  <td className="px-2 py-2.5 text-white">{pick.pick}</td>
                                  <td className="px-2 py-2.5 text-slate-400">{pick.opponent}</td>
                                  <td className="px-2 py-2.5 text-right text-slate-300">{pick.odds}</td>
                                  <td className={`px-2 py-2.5 text-center font-medium uppercase ${resultColor}`}>{pick.result}</td>
                                  <td className={`px-2 py-2.5 text-right font-medium ${plColor}`}>
                                    {pick.pl > 0 ? "+" : ""}{pick.pl.toFixed(2)}u
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-400">No individual pick data available for this event.</p>
                    )}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </SurfaceCard>
    </div>
  )
}
