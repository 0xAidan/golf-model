import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Brain, CircleAlert, Clock3, Flag, NotebookPen, Radar, ShieldAlert, Sparkles, TrendingUp } from "lucide-react"
import { Route, Routes } from "react-router-dom"

import { BarTrendChart, SparklineChart } from "@/components/charts"
import { CommandShell, MetricTile, SectionTitle, SurfaceCard } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { formatDateTime, formatNumber, formatUnits } from "@/lib/format"
import { useLocalStorageState } from "@/lib/storage"
import type {
  CompositePlayer,
  DashboardState,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  LiveRefreshStatusResponse,
  MatchupBet,
  PlayerProfile,
  PredictionRunRequest,
  PredictionRunResponse,
  ResearchProposal,
} from "@/lib/types"

const DEFAULT_REQUEST: PredictionRunRequest = {
  tour: "pga",
  tournament: "",
  course: "",
  mode: "full",
  enable_ai: true,
}

function App() {
  const queryClient = useQueryClient()
  const [predictionRequest] = useLocalStorageState<PredictionRunRequest>("golf-model.prediction-request", DEFAULT_REQUEST)
  const [predictionRun] = useLocalStorageState<PredictionRunResponse | null>("golf-model.latest-prediction-run", null)
  const [matchupSearch, setMatchupSearch] = useLocalStorageState("golf-model.matchup-search", "")
  const [minEdge, setMinEdge] = useLocalStorageState("golf-model.min-edge", 0.02)
  const [selectedBooks, setSelectedBooks] = useLocalStorageState<string[]>("golf-model.selected-books", [])
  const [predictionLayout, setPredictionLayout] = useLocalStorageState<"board" | "table" | "players">("golf-model.prediction-layout", "board")
  const [selectedPlayerKey, setSelectedPlayerKey] = useLocalStorageState("golf-model.selected-player", "")
  const [selectedMatchupKey, setSelectedMatchupKey] = useLocalStorageState("golf-model.selected-matchup", "")

  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    refetchInterval: 30_000,
  })
  const gradingHistoryQuery = useQuery({
    queryKey: ["grading-history"],
    queryFn: api.getGradingHistory,
  })
  const researchQuery = useQuery({
    queryKey: ["research-proposals"],
    queryFn: api.getResearchProposals,
  })
  const liveRefreshStatusQuery = useQuery({
    queryKey: ["live-refresh-status"],
    queryFn: api.getLiveRefreshStatus,
    refetchInterval: (query) => {
      const data = query.state.data as LiveRefreshStatusResponse | undefined
      return data?.status?.running ? 5_000 : 15_000
    },
  })
  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    refetchInterval: 10_000,
  })
  const [predictionTab, setPredictionTab] = useState<"live" | "upcoming">("live")
  const liveSnapshot = (liveSnapshotQuery.data?.snapshot ?? null) as LiveRefreshSnapshot | null
  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)
  const hydratedRun = useMemo(() => buildHydratedPredictionRun(liveSnapshot), [liveSnapshot])
  const effectivePredictionRun = predictionRun ?? hydratedRun
  const normalizedSelectedBooks = useMemo(
    () => selectedBooks.map((book) => normalizeSportsbook(book)).filter(Boolean),
    [selectedBooks],
  )
  const selectedBookSet = useMemo(() => new Set(normalizedSelectedBooks), [normalizedSelectedBooks])
  const availableBooks = useMemo(
    () => collectAvailableBooks(effectivePredictionRun, liveSnapshot),
    [effectivePredictionRun, liveSnapshot],
  )
  const playerProfileQuery = useQuery({
    queryKey: ["player-profile", selectedPlayerKey, effectivePredictionRun?.tournament_id, effectivePredictionRun?.course_num],
    queryFn: () => api.getPlayerProfile(selectedPlayerKey, effectivePredictionRun?.tournament_id ?? 0, effectivePredictionRun?.course_num),
    enabled: Boolean(selectedPlayerKey && effectivePredictionRun?.tournament_id),
  })

  const gradeMutation = useMutation({
    mutationFn: () => api.gradeLatestTournament(dashboardQuery.data?.latest_completed_event ?? undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
    },
  })

  const players = effectivePredictionRun?.composite_results ?? []
  const filteredMatchups = useMemo(() => {
    const sourceMatchups = effectivePredictionRun?.matchup_bets ?? []
    return sourceMatchups.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      const passesBook = selectedBookSet.size === 0 || selectedBookSet.has(matchupBook)
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesBook && passesSearch && matchup.ev >= minEdge
    })
  }, [effectivePredictionRun?.matchup_bets, matchupSearch, minEdge, selectedBookSet])

  const selectedPlayer = players.find((player) => player.player_key === selectedPlayerKey) ?? players[0] ?? null
  const selectedMatchup =
    filteredMatchups.find((matchup) => buildMatchupKey(matchup) === selectedMatchupKey) ??
    filteredMatchups[0] ??
    null

  const secondaryBets = flattenSecondaryBets(effectivePredictionRun)
  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const proposals = researchQuery.data ?? []
  const dashboard = dashboardQuery.data as DashboardState | undefined

  useEffect(() => {
    const ensureAlwaysOnRuntime = async () => {
      try {
        const runtime = await api.getLiveRefreshStatus()
        const settings = runtime.settings ?? {}
        if (settings.enabled === false) {
          return
        }
        const tour = settings.tour || predictionRequest.tour || "pga"
        if (settings.autostart !== true) {
          await api.patchAutoresearchSettings({
            live_refresh: { ...settings, enabled: true, autostart: true, tour },
          })
        }
        if (!runtime.status?.running) {
          await api.startLiveRefresh({
            tour,
            live_refresh: { ...settings, enabled: true, autostart: true, tour },
          })
        }
      } catch {
        // Keep UI rendering even if bootstrap check fails.
      }
    }
    void ensureAlwaysOnRuntime()
  }, [predictionRequest.tour])

  return (
    <CommandShell
      headline={effectivePredictionRun?.event_name ?? "Operator command station"}
      subheadline="Desktop-first betting intelligence across predictions, player drill-downs, course context, grading continuity, and research control."
      actions={
        <>
          <Button
            size="lg"
            variant="outline"
            onClick={() => gradeMutation.mutate()}
            disabled={gradeMutation.isPending}
          >
            {gradeMutation.isPending ? "Grading..." : "Grade latest event"}
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ["live-refresh-status"] })
              void queryClient.invalidateQueries({ queryKey: ["live-refresh-snapshot"] })
            }}
          >
            {liveRuntimeRunning ? "Refresh live board" : "Check runtime"}
          </Button>
        </>
      }
    >
      <Routes>
        <Route
          path="/"
          element={
            <PredictionWorkspacePage
              dashboard={dashboard}
              liveSnapshot={liveSnapshot}
              liveRuntimeRunning={liveRuntimeRunning}
              predictionTab={predictionTab}
              onPredictionTabChange={setPredictionTab}
              availableBooks={availableBooks}
              selectedBooks={normalizedSelectedBooks}
              onSelectedBooksChange={setSelectedBooks}
              filteredMatchups={filteredMatchups}
              gradingHistory={gradingHistory}
              layout={predictionLayout}
              minEdge={minEdge}
              matchupSearch={matchupSearch}
              onLayoutChange={setPredictionLayout}
              onMinEdgeChange={setMinEdge}
              onMatchupSearchChange={setMatchupSearch}
              onPlayerSelect={setSelectedPlayerKey}
              onMatchupSelect={setSelectedMatchupKey}
              players={players}
              predictionRun={effectivePredictionRun}
              secondaryBets={secondaryBets}
              selectedPlayer={selectedPlayer}
              selectedMatchup={selectedMatchup}
            />
          }
        />
        <Route
          path="/players"
          element={
            <PlayersPage
              players={players}
              selectedPlayer={selectedPlayer}
              selectedPlayerProfile={playerProfileQuery.data}
              onPlayerSelect={setSelectedPlayerKey}
            />
          }
        />
        <Route
          path="/matchups"
          element={
            <MatchupsPage
              matchups={filteredMatchups}
              onMatchupSelect={setSelectedMatchupKey}
              selectedMatchup={selectedMatchup}
            />
          }
        />
        <Route
          path="/course"
          element={
            <CoursePage
              dashboard={dashboard}
              players={players}
              predictionRun={effectivePredictionRun}
            />
          }
        />
        <Route
          path="/grading"
          element={<GradingPage gradingHistory={gradingHistory} />}
        />
        <Route
          path="/history"
          element={<HistoryPage dashboard={dashboard} gradingHistory={gradingHistory} />}
        />
        <Route
          path="/research"
          element={<ResearchPage dashboard={dashboard} proposals={proposals} />}
        />
      </Routes>
    </CommandShell>
  )
}

function PredictionWorkspacePage({
  dashboard,
  liveSnapshot,
  liveRuntimeRunning,
  predictionTab,
  onPredictionTabChange,
  availableBooks,
  selectedBooks,
  onSelectedBooksChange,
  filteredMatchups,
  gradingHistory,
  layout,
  minEdge,
  matchupSearch,
  onLayoutChange,
  onMinEdgeChange,
  onMatchupSearchChange,
  onPlayerSelect,
  onMatchupSelect,
  players,
  predictionRun,
  secondaryBets,
  selectedPlayer,
  selectedMatchup,
}: {
  dashboard?: DashboardState
  liveSnapshot: LiveRefreshSnapshot | null
  liveRuntimeRunning: boolean
  predictionTab: "live" | "upcoming"
  onPredictionTabChange: (value: "live" | "upcoming") => void
  availableBooks: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
  filteredMatchups: MatchupBet[]
  gradingHistory: GradedTournamentSummary[]
  layout: "board" | "table" | "players"
  minEdge: number
  matchupSearch: string
  onLayoutChange: (value: "board" | "table" | "players") => void
  onMinEdgeChange: (value: number) => void
  onMatchupSearchChange: (value: string) => void
  onPlayerSelect: (value: string) => void
  onMatchupSelect: (value: string) => void
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
  secondaryBets: Array<{ market: string; player: string; odds: string; ev: number; confidence?: string }>
  selectedPlayer: CompositePlayer | null
  selectedMatchup: MatchupBet | null
}) {
  const totalProfit = gradingHistory.reduce((sum, tournament) => sum + Number(tournament.total_profit ?? 0), 0)
  const liveTournament = liveSnapshot?.live_tournament
  const upcomingTournament = liveSnapshot?.upcoming_tournament
  const selectedBookSet = new Set(selectedBooks)
  const liveLabel = !liveSnapshot
    ? "Live status unavailable"
    : liveTournament?.active
      ? "Live Event"
      : "Completed Event"
  const liveRankings = (liveTournament?.rankings ?? []).filter((row) => !isCutFinishState(row.finish_state))
  const liveMatchups = (liveTournament?.matchups ?? []).filter((row) => {
    const normalized = normalizeSportsbook(row.bookmaker)
    return selectedBookSet.size === 0 || selectedBookSet.has(normalized)
  })
  const upcomingRankings = upcomingTournament?.rankings ?? []
  const upcomingMatchups = (upcomingTournament?.matchups ?? []).filter((row) => {
    const normalized = normalizeSportsbook(row.bookmaker)
    return selectedBookSet.size === 0 || selectedBookSet.has(normalized)
  })

  return (
    <div className="space-y-6">
      <SurfaceCard>
        <SectionTitle
          title="Prediction stream"
          description="Always-on runtime auto-detects live, upcoming, and past event context."
          action={
            <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${liveRuntimeRunning ? "bg-emerald-500/15 text-emerald-200" : "bg-amber-500/15 text-amber-200"}`}>
              {liveRuntimeRunning ? "Runtime active" : "Runtime booting"}
            </span>
          }
        />
        <div className="mb-4 flex gap-2">
          <Button
            size="sm"
            variant={predictionTab === "live" ? "default" : "outline"}
            onClick={() => onPredictionTabChange("live")}
          >
            {liveLabel}
          </Button>
          <Button
            size="sm"
            variant={predictionTab === "upcoming" ? "default" : "outline"}
            onClick={() => onPredictionTabChange("upcoming")}
          >
            Upcoming Event
          </Button>
        </div>
        <BookFilterBar
          books={availableBooks}
          selectedBooks={selectedBooks}
          onSelectedBooksChange={onSelectedBooksChange}
        />
        {predictionTab === "live" ? (
          <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{liveLabel} leaderboard</p>
              <p className="mt-2 text-sm text-slate-300">{liveTournament?.event_name ?? "Waiting for event context..."}</p>
              <p className="mt-1 text-xs text-slate-500">Cut and withdrawn players are hidden.</p>
              <div className="mt-4 max-h-[360px] overflow-auto rounded-xl border border-white/8">
                <table className="w-full border-collapse text-sm">
                  <thead className="bg-white/6 text-xs uppercase tracking-[0.16em] text-slate-400">
                    <tr>
                      <th className="px-3 py-2 text-left">#</th>
                      <th className="px-3 py-2 text-left">Player</th>
                      <th className="px-3 py-2 text-left">Composite</th>
                      <th className="px-3 py-2 text-left">Form</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveRankings.length ? (
                      liveRankings.slice(0, 30).map((row) => (
                        <tr key={`${row.player_key ?? row.player}-${row.rank}`} className="border-t border-white/8 text-slate-200">
                          <td className="px-3 py-2">{row.rank}</td>
                          <td className="px-3 py-2 text-white">{row.player}</td>
                          <td className="px-3 py-2">{formatNumber(row.composite, 2)}</td>
                          <td className="px-3 py-2">{formatNumber(row.form, 2)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="px-3 py-3 text-slate-400" colSpan={4}>
                          No rankings yet. Runtime is still collecting data.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live matchups</p>
              <p className="mt-2 text-sm text-slate-300">
                Best currently surfaced opportunities from always-on scans.
                {selectedBooks.length ? ` Showing ${liveMatchups.length} after book filter.` : ""}
              </p>
              <div className="mt-4 space-y-2">
                {liveMatchups.length ? (
                  liveMatchups.slice(0, 20).map((row, index) => (
                    <div key={`${row.player}-${row.opponent}-${index}`} className="rounded-xl border border-white/8 bg-black/25 px-3 py-2">
                      <p className="text-sm font-medium text-white">
                        {row.player} over {row.opponent}
                      </p>
                      <p className="text-xs text-slate-400">
                        {row.market_odds ?? "--"} · {row.bookmaker ?? "book unknown"} · EV {formatNumber((row.ev ?? 0) * 100, 1)}%
                      </p>
                    </div>
                  ))
                ) : (
                  <EmptyState message="No live matchup edges yet." />
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Upcoming board</p>
              <p className="mt-2 text-sm text-slate-300">{upcomingTournament?.event_name ?? "Waiting for next event..."}</p>
              <div className="mt-4 max-h-[360px] overflow-auto rounded-xl border border-white/8">
                <table className="w-full border-collapse text-sm">
                  <thead className="bg-white/6 text-xs uppercase tracking-[0.16em] text-slate-400">
                    <tr>
                      <th className="px-3 py-2 text-left">#</th>
                      <th className="px-3 py-2 text-left">Player</th>
                      <th className="px-3 py-2 text-left">Composite</th>
                      <th className="px-3 py-2 text-left">Course</th>
                    </tr>
                  </thead>
                  <tbody>
                    {upcomingRankings.length ? (
                      upcomingRankings.slice(0, 30).map((row) => (
                        <tr key={`${row.player_key ?? row.player}-${row.rank}`} className="border-t border-white/8 text-slate-200">
                          <td className="px-3 py-2">{row.rank}</td>
                          <td className="px-3 py-2 text-white">{row.player}</td>
                          <td className="px-3 py-2">{formatNumber(row.composite, 2)}</td>
                          <td className="px-3 py-2">{formatNumber(row.course_fit, 2)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="px-3 py-3 text-slate-400" colSpan={4}>
                          No upcoming rankings yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Upcoming event matchups</p>
              <p className="mt-2 text-sm text-slate-300">
                Early lines for the next event as books publish more pairs.
                {selectedBooks.length ? ` Showing ${upcomingMatchups.length} after book filter.` : ""}
              </p>
              <div className="mt-4 space-y-2">
                {upcomingMatchups.length ? (
                  upcomingMatchups.slice(0, 20).map((row, index) => (
                    <div key={`${row.player}-${row.opponent}-${index}`} className="rounded-xl border border-white/8 bg-black/25 px-3 py-2">
                      <p className="text-sm font-medium text-white">
                        {row.player} over {row.opponent}
                      </p>
                      <p className="text-xs text-slate-400">
                        {row.market_odds ?? "--"} · {row.bookmaker ?? "book unknown"} · EV {formatNumber((row.ev ?? 0) * 100, 1)}%
                      </p>
                    </div>
                  ))
                ) : (
                  <EmptyState message="No upcoming matchup edges yet." />
                )}
              </div>
            </div>
          </div>
        )}
      </SurfaceCard>

      <div className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Field size" value={String(predictionRun?.field_size ?? 0)} detail={predictionRun?.event_name ?? "No run loaded"} />
        <MetricTile label="Matchups" value={String(filteredMatchups.length)} detail="Bread-and-butter board after live filters" />
        <MetricTile label="Secondary edges" value={String(secondaryBets.length)} detail="Placements, miss-cut, and adjacent markets" />
        <MetricTile label="Season P/L" value={formatUnits(totalProfit)} detail="From durable grading history" tone={totalProfit >= 0 ? "positive" : "warning"} />
      </div>

      <div className="grid gap-6 2xl:grid-cols-[1.35fr_minmax(380px,0.9fr)]">
        <SurfaceCard className="min-w-0">
          <SectionTitle
            title="Matchup board"
            description="Every recommended matchup is filterable and opens an explainability panel instead of a flat markdown line."
            action={
              <div className="flex flex-wrap gap-2">
                {(["board", "table", "players"] as const).map((option) => (
                  <Button
                    key={option}
                    size="sm"
                    variant={layout === option ? "default" : "outline"}
                    onClick={() => onLayoutChange(option)}
                  >
                    {option}
                  </Button>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!predictionRun?.card_content) {
                      return
                    }
                    const blob = new Blob([predictionRun.card_content], { type: "text/markdown;charset=utf-8" })
                    const url = URL.createObjectURL(blob)
                    const anchor = document.createElement("a")
                    anchor.href = url
                    anchor.download = `${predictionRun.event_name ?? "prediction"}.md`
                    anchor.click()
                    URL.revokeObjectURL(url)
                  }}
                >
                  Export markdown
                </Button>
              </div>
            }
          />
          <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px]">
            <LabeledInput label="Search players" value={matchupSearch} onChange={onMatchupSearchChange} />
            <LabeledInput
              label="Min EV"
              value={String(minEdge)}
              onChange={(value) => onMinEdgeChange(Number(value) || 0)}
              type="number"
            />
          </div>
          {layout === "board" ? (
            <div className="grid gap-3 xl:grid-cols-2">
              {filteredMatchups.length ? (
                filteredMatchups.map((matchup) => (
                  <button
                    key={buildMatchupKey(matchup)}
                    type="button"
                    className="rounded-2xl border border-white/8 bg-black/20 p-4 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
                    onClick={() => {
                      onMatchupSelect(buildMatchupKey(matchup))
                      onPlayerSelect(matchup.pick_key)
                    }}
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="font-medium text-white">{matchup.pick}</p>
                        <p className="text-xs text-slate-500">vs {matchup.opponent}</p>
                      </div>
                      <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">
                        {matchup.tier ?? "lean"}
                      </span>
                    </div>
                    <div className="mt-4 grid grid-cols-4 gap-3 text-sm">
                      <div>
                        <p className="text-slate-500">Edge</p>
                        <p className="font-semibold text-cyan-200">{matchup.ev_pct}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Price</p>
                        <p className="font-semibold text-white">{matchup.odds}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Gap</p>
                        <p className="font-semibold text-white">{formatNumber(matchup.composite_gap, 1)}</p>
                      </div>
                      <div>
                        <p className="text-slate-500">Conviction</p>
                        <p className="font-semibold text-white">{formatNumber(matchup.conviction, 0)}</p>
                      </div>
                    </div>
                  </button>
                ))
              ) : (
                <div className="xl:col-span-2">
                  <EmptyState message="No matchup rows match current search/EV/book filters." />
                </div>
              )}
            </div>
          ) : layout === "table" ? (
            <div className="overflow-hidden rounded-2xl border border-white/10">
              {filteredMatchups.length ? (
                <table className="w-full border-collapse text-left text-sm">
                  <thead className="bg-white/6 text-xs uppercase tracking-[0.18em] text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Pick</th>
                      <th className="px-4 py-3">Edge</th>
                      <th className="px-4 py-3">Price</th>
                      <th className="px-4 py-3">Model</th>
                      <th className="px-4 py-3">Implied</th>
                      <th className="px-4 py-3">Form gap</th>
                      <th className="px-4 py-3">Course gap</th>
                      <th className="px-4 py-3">Conviction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMatchups.map((matchup) => (
                      <tr
                        key={buildMatchupKey(matchup)}
                        className="cursor-pointer border-t border-white/6 text-slate-200 transition hover:bg-white/6"
                        onClick={() => {
                          onMatchupSelect(buildMatchupKey(matchup))
                          onPlayerSelect(matchup.pick_key)
                        }}
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium text-white">{matchup.pick}</div>
                          <div className="text-xs text-slate-500">vs {matchup.opponent}</div>
                        </td>
                        <td className="px-4 py-3 text-cyan-200">{matchup.ev_pct}</td>
                        <td className="px-4 py-3">{matchup.odds}</td>
                        <td className="px-4 py-3">{`${(matchup.model_win_prob * 100).toFixed(1)}%`}</td>
                        <td className="px-4 py-3">{`${(matchup.implied_prob * 100).toFixed(1)}%`}</td>
                        <td className="px-4 py-3">{formatNumber(matchup.form_gap, 1)}</td>
                        <td className="px-4 py-3">{formatNumber(matchup.course_fit_gap, 1)}</td>
                        <td className="px-4 py-3">{formatNumber(matchup.conviction, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState message="No matchup rows match current search/EV/book filters." />
              )}
            </div>
          ) : (
            <div className="grid gap-3">
              {players.length ? (
                players.slice(0, 12).map((player) => (
                  <button
                    key={player.player_key}
                    type="button"
                    className="rounded-2xl border border-white/8 bg-black/20 p-4 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
                    onClick={() => onPlayerSelect(player.player_key)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-medium text-white">
                          #{player.rank} {player.player_display}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          composite {formatNumber(player.composite, 1)} • momentum {formatNumber(player.momentum, 1)}
                        </p>
                      </div>
                      <span className="rounded-full bg-white/6 px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
                        {player.momentum_direction ?? "steady"}
                      </span>
                    </div>
                  </button>
                ))
              ) : (
                <EmptyState message="No players are loaded for this context yet." />
              )}
            </div>
          )}
        </SurfaceCard>

        <SurfaceCard>
          <SectionTitle
            title="Selected matchup intelligence"
            description="Edge, pricing gap, score component deltas, and portfolio context in one place."
          />
          {selectedMatchup ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-cyan-400/15 bg-cyan-400/10 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-cyan-100/70">Current play</p>
                    <h4 className="mt-2 text-xl font-semibold text-white">
                      {selectedMatchup.pick} over {selectedMatchup.opponent}
                    </h4>
                  </div>
                  <div className="rounded-2xl bg-black/25 px-3 py-2 text-right">
                    <p className="text-xs uppercase tracking-[0.18em] text-cyan-100/70">Model edge</p>
                    <p className="mt-1 text-lg font-semibold text-cyan-200">{selectedMatchup.ev_pct}</p>
                  </div>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-200">{selectedMatchup.reason}</p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <MetricTile label="Model win probability" value={`${(selectedMatchup.model_win_prob * 100).toFixed(1)}%`} />
                <MetricTile label="Market implied" value={`${(selectedMatchup.implied_prob * 100).toFixed(1)}%`} />
                <MetricTile label="Composite gap" value={formatNumber(selectedMatchup.composite_gap, 1)} />
                <MetricTile label="Momentum alignment" value={selectedMatchup.momentum_aligned ? "Aligned" : "Mixed"} />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <MetricTile label="Form gap" value={formatNumber(selectedMatchup.form_gap, 1)} />
                <MetricTile label="Course-fit gap" value={formatNumber(selectedMatchup.course_fit_gap, 1)} />
                <MetricTile label="Stake multiplier" value={formatNumber(selectedMatchup.stake_multiplier, 2)} />
                <MetricTile label="Book" value={selectedMatchup.book ?? "--"} />
              </div>
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="mb-2 flex items-center gap-2 text-slate-300">
                  <ChartColumnIcon />
                  <span className="text-sm font-medium">Confidence drivers</span>
                </div>
                <BarTrendChart
                  labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
                  values={[
                    selectedMatchup.composite_gap,
                    selectedMatchup.form_gap,
                    selectedMatchup.course_fit_gap,
                    Number(selectedMatchup.pick_momentum ?? 0) - Number(selectedMatchup.opp_momentum ?? 0),
                    Number(selectedMatchup.conviction ?? 0),
                  ]}
                  color="#22d3ee"
                />
              </div>
              {selectedPlayer ? (
                <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Selected player context</p>
                  <p className="mt-2 text-lg font-semibold text-white">{selectedPlayer.player_display}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-300">
                    Composite {formatNumber(selectedPlayer.composite, 1)} with form {formatNumber(selectedPlayer.form, 1)}, course fit {formatNumber(selectedPlayer.course_fit, 1)}, and momentum {formatNumber(selectedPlayer.momentum, 1)}.
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <EmptyState message="Run a prediction to inspect matchup explainability." />
          )}
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SurfaceCard>
          <SectionTitle
            title="Player ladder"
            description="The operator list keeps the top of the board visible while letting you pivot into player drill-downs."
          />
          <div className="space-y-2">
            {players.length ? (
              players.slice(0, 12).map((player) => (
                <button
                  key={player.player_key}
                  type="button"
                  className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
                  onClick={() => onPlayerSelect(player.player_key)}
                >
                  <div>
                    <p className="font-medium text-white">
                      #{player.rank} {player.player_display}
                    </p>
                    <p className="text-xs text-slate-500">
                      form {formatNumber(player.form, 1)} • course {formatNumber(player.course_fit, 1)} • momentum {formatNumber(player.momentum, 1)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</p>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">composite</p>
                  </div>
                </button>
              ))
            ) : (
              <EmptyState message="No player ladder is available yet. Run is still warming up." />
            )}
          </div>
        </SurfaceCard>

        <SurfaceCard>
          <SectionTitle
            title="Secondary market rail"
            description="Placements and adjacent angles stay visible without overwhelming the matchup-first workflow."
          />
          <div className="space-y-3">
            {secondaryBets.length ? (
              secondaryBets.slice(0, 8).map((bet) => (
                <div key={`${bet.market}-${bet.player}-${bet.odds}`} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-white">{bet.player}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className="rounded-full bg-white/8 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300">
                          {bet.market}
                        </span>
                        <span className="rounded-full bg-cyan-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-200">
                          {secondaryBadgeLabel(bet.market)}
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-cyan-200">{formatNumber(bet.ev * 100, 1)}% EV</p>
                      <p className="text-xs text-slate-500">{bet.odds}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState message="No secondary market edges surfaced on the current run." />
            )}
          </div>
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <SurfaceCard>
          <SectionTitle
            title="Coverage and run health"
            description="Major-week LIV coverage, run quality, and export provenance stay visible before you trust the board."
          />
          <div className="space-y-3">
            <InfoRow icon={ShieldAlert} label="Field validation" value={predictionRun?.field_validation?.has_cross_tour_field_risk ? "Review warnings" : "Healthy"} />
            <InfoRow icon={Flag} label="Latest completed event" value={dashboard?.latest_completed_event?.event_name ?? "--"} />
            <InfoRow icon={Clock3} label="Last graded tournament" value={dashboard?.latest_graded_tournament?.name ?? "--"} />
            <InfoRow icon={Brain} label="AI availability" value={dashboard?.ai_status?.available ? "Enabled" : "Unavailable"} />
          </div>
          {predictionRun?.warnings?.length ? (
            <div className="mt-4 rounded-2xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm text-amber-100">
              {predictionRun.warnings.join(" ")}
            </div>
          ) : null}
        </SurfaceCard>

        <SurfaceCard>
          <SectionTitle
            title="Markdown export preview"
            description="Markdown remains available as an export mode rather than the primary operating surface."
          />
          <div className="max-h-[320px] overflow-auto rounded-2xl border border-white/10 bg-black/30 p-4">
            <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-300">
              {predictionRun?.card_content ?? "Run a prediction to generate a fresh markdown artifact."}
            </pre>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function PlayersPage({
  players,
  selectedPlayer,
  selectedPlayerProfile,
  onPlayerSelect,
}: {
  players: CompositePlayer[]
  selectedPlayer: CompositePlayer | null
  selectedPlayerProfile?: PlayerProfile
  onPlayerSelect: (playerKey: string) => void
}) {
  const recentTrend = (selectedPlayerProfile?.recent_rounds ?? []).map((round) => Number(round.sg_total ?? 0)).reverse()
  const momentumValues =
    recentTrend.length > 0
      ? recentTrend
      : (selectedPlayer
          ? [
              selectedPlayer.course_fit,
              selectedPlayer.form,
              selectedPlayer.momentum,
              selectedPlayer.composite,
            ]
          : [])
  const courseValues = selectedPlayerProfile?.course_history.map((round) => Number(round.sg_total ?? 0)).reverse() ?? []

  return (
    <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
      <SurfaceCard>
        <SectionTitle title="Projection ladder" description="Click any player to open a richer projection profile with score components and momentum context." />
        <div className="space-y-2">
          {players.length ? (
            players.map((player) => (
              <button
                key={player.player_key}
                type="button"
                className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
                onClick={() => onPlayerSelect(player.player_key)}
              >
                <div>
                  <p className="font-medium text-white">{player.player_display}</p>
                  <p className="text-xs text-slate-500">rank #{player.rank}</p>
                </div>
                <p className="text-sm font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</p>
              </button>
            ))
          ) : (
            <EmptyState message="No players available yet for this event context." />
          )}
        </div>
      </SurfaceCard>
      <SurfaceCard>
        <SectionTitle title="Player profile" description="Current-week projection context, momentum, course confidence, and sub-score detail." />
        {selectedPlayer ? (
          <div className="space-y-5">
            <div className="grid gap-4 md:grid-cols-4">
              <MetricTile label="Composite" value={formatNumber(selectedPlayer.composite, 1)} />
              <MetricTile label="Course fit" value={formatNumber(selectedPlayer.course_fit, 1)} />
              <MetricTile label="Form" value={formatNumber(selectedPlayer.form, 1)} />
              <MetricTile label="Momentum" value={formatNumber(selectedPlayer.momentum, 1)} />
            </div>
            <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
              <div className="mb-2 flex items-center gap-2 text-slate-300">
                <TrendingUp className="h-4 w-4 text-cyan-200" />
                <span className="text-sm font-medium">Recent strokes-gained trend</span>
              </div>
              <SparklineChart values={momentumValues} color="#5eead4" />
            </div>
            {courseValues.length ? (
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="mb-2 flex items-center gap-2 text-slate-300">
                  <Flag className="h-4 w-4 text-cyan-200" />
                  <span className="text-sm font-medium">Course-history trend</span>
                </div>
                <SparklineChart values={courseValues} color="#60a5fa" />
              </div>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2">
              <MetricTile label="Momentum direction" value={selectedPlayer.momentum_direction ?? "--"} />
              <MetricTile label="Course confidence" value={formatNumber(selectedPlayer.course_confidence, 2)} />
              <MetricTile label="Course rounds" value={String(selectedPlayer.course_rounds ?? 0)} />
              <MetricTile label="Weather adj." value={formatNumber(selectedPlayer.weather_adjustment, 1)} />
            </div>
            {selectedPlayerProfile?.linked_bets?.length ? (
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <h4 className="mb-3 text-sm font-semibold text-white">Linked bets</h4>
                <div className="space-y-3">
                  {selectedPlayerProfile.linked_bets.slice(0, 6).map((bet, index) => (
                    <div key={`${bet.bet_type}-${index}`} className="flex items-center justify-between gap-4 rounded-2xl border border-white/6 px-3 py-3">
                      <div>
                        <p className="text-sm font-medium text-white">{bet.bet_type ?? "bet"}</p>
                        <p className="text-xs text-slate-500">
                          {bet.player_display}
                          {bet.opponent_display ? ` vs ${bet.opponent_display}` : ""}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-cyan-200">{bet.market_odds ?? "--"}</p>
                        <p className="text-xs text-slate-500">{bet.confidence ?? "quant"}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <ComponentTable title="Course components" components={selectedPlayer.details?.course_components} />
            <ComponentTable title="Form components" components={selectedPlayer.details?.form_components} />
            <ComponentTable title="Momentum windows" components={selectedPlayer.details?.momentum_windows} />
            <MetricsCategoryTable title="Current market context" categories={selectedPlayerProfile?.current_metrics} />
          </div>
        ) : (
          <EmptyState message="Run a prediction to load player projections." />
        )}
      </SurfaceCard>
    </div>
  )
}

function MatchupsPage({
  matchups,
  onMatchupSelect,
  selectedMatchup,
}: {
  matchups: MatchupBet[]
  onMatchupSelect: (key: string) => void
  selectedMatchup: MatchupBet | null
}) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[1fr_0.9fr]">
      <SurfaceCard>
        <SectionTitle title="Matchup conviction map" description="Scan tier, edge, pricing, and momentum at a glance." />
        <div className="grid gap-3 xl:grid-cols-2">
          {matchups.length ? (
            matchups.map((matchup) => (
              <button
                key={buildMatchupKey(matchup)}
                type="button"
                onClick={() => onMatchupSelect(buildMatchupKey(matchup))}
                className="rounded-2xl border border-white/8 bg-black/20 p-4 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-white">{matchup.pick}</p>
                    <p className="text-xs text-slate-500">vs {matchup.opponent}</p>
                  </div>
                  <span className="rounded-full bg-cyan-400/12 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">
                    {matchup.tier ?? "lean"}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <p className="text-slate-500">Edge</p>
                    <p className="font-semibold text-cyan-200">{matchup.ev_pct}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Price</p>
                    <p className="font-semibold text-white">{matchup.odds}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">Conviction</p>
                    <p className="font-semibold text-white">{formatNumber(matchup.conviction, 0)}</p>
                  </div>
                </div>
              </button>
            ))
          ) : (
            <div className="xl:col-span-2">
              <EmptyState message="No matchups available under the current filters." />
            </div>
          )}
        </div>
      </SurfaceCard>
      <SurfaceCard>
        <SectionTitle title="Detailed edge breakdown" description="Why the board picked this side, and how aggressive the edge really is." />
        {selectedMatchup ? (
          <div className="space-y-4">
            <MetricTile label="Recommended side" value={selectedMatchup.pick} detail={`over ${selectedMatchup.opponent}`} />
            <MetricTile label="Reason" value={selectedMatchup.reason} detail={selectedMatchup.book ? `book: ${selectedMatchup.book}` : undefined} />
            <div className="grid gap-4 md:grid-cols-2">
              <MetricTile label="Model probability" value={`${(selectedMatchup.model_win_prob * 100).toFixed(1)}%`} />
              <MetricTile label="Implied probability" value={`${(selectedMatchup.implied_prob * 100).toFixed(1)}%`} />
              <MetricTile label="Form gap" value={formatNumber(selectedMatchup.form_gap, 1)} />
              <MetricTile label="Momentum pairing" value={selectedMatchup.momentum_aligned ? "Aligned" : "Mixed"} />
            </div>
            <BarTrendChart
              labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
              values={[
                selectedMatchup.composite_gap,
                selectedMatchup.form_gap,
                selectedMatchup.course_fit_gap,
                Number(selectedMatchup.pick_momentum ?? 0) - Number(selectedMatchup.opp_momentum ?? 0),
                Number(selectedMatchup.conviction ?? 0),
              ]}
              color="#38bdf8"
            />
          </div>
        ) : (
          <EmptyState message="Select a matchup from the board to inspect it." />
        )}
      </SurfaceCard>
    </div>
  )
}

function CoursePage({
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
            <InfoRow icon={ShieldAlert} label="Thin-round players" value={String(predictionRun?.field_validation?.players_with_thin_rounds.length ?? 0)} />
            <InfoRow icon={CircleAlert} label="Missing DG skill" value={String(predictionRun?.field_validation?.players_missing_dg_skill.length ?? 0)} />
            <InfoRow icon={NotebookPen} label="Prediction artifact" value={dashboard?.latest_prediction_artifact?.path ?? "--"} />
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function GradingPage({ gradingHistory }: { gradingHistory: GradedTournamentSummary[] }) {
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

function HistoryPage({
  dashboard,
  gradingHistory,
}: {
  dashboard?: DashboardState
  gradingHistory: GradedTournamentSummary[]
}) {
  const outputCards = [
    dashboard?.latest_prediction_artifact,
    dashboard?.latest_backtest_artifact,
    dashboard?.latest_research_artifact,
  ].filter(Boolean)

  return (
    <div className="grid gap-6 2xl:grid-cols-[1fr_0.95fr]">
      <SurfaceCard>
        <SectionTitle title="Artifact history" description="Recent prediction, backtest, and research artifacts with readable summaries for quick context." />
        <div className="space-y-3">
          {outputCards.map((artifact) => (
            <div key={artifact?.path} className="rounded-2xl border border-white/8 bg-black/20 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{artifact?.type ?? "artifact"}</p>
              <p className="mt-2 font-medium text-white">{artifact?.path}</p>
              <pre className="mt-3 whitespace-pre-wrap text-xs leading-6 text-slate-400">
                {JSON.stringify(artifact?.summary ?? {}, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </SurfaceCard>
      <SurfaceCard>
        <SectionTitle title="Performance snapshot" description="Fast answers to whether the system is trending up, flat, or under stress." />
        <div className="grid gap-4 md:grid-cols-2">
          <MetricTile label="Total profit" value={formatUnits(gradingHistory.reduce((sum, item) => sum + Number(item.total_profit ?? 0), 0))} />
          <MetricTile label="Events tracked" value={String(gradingHistory.length)} />
          <MetricTile label="Latest artifact" value={dashboard?.latest_prediction_artifact?.path ?? "--"} />
          <MetricTile label="Latest completed event" value={dashboard?.latest_completed_event?.event_name ?? "--"} />
        </div>
      </SurfaceCard>
    </div>
  )
}

function ResearchPage({
  dashboard,
  proposals,
}: {
  dashboard?: DashboardState
  proposals: ResearchProposal[]
}) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
      <SurfaceCard>
        <SectionTitle title="Autoresearch status" description="Powerful, but visually subordinate to prediction and grading so the operator flow stays clean." />
        <div className="grid gap-4 md:grid-cols-2">
          <MetricTile label="Runtime" value={dashboard?.autoresearch?.running ? "Running" : "Idle"} />
          <MetricTile label="Run count" value={String(dashboard?.autoresearch?.run_count ?? 0)} />
          <MetricTile label="Last finished" value={formatDateTime(dashboard?.autoresearch?.last_finished_at)} />
          <MetricTile label="Latest research artifact" value={dashboard?.latest_research_artifact?.path ?? "--"} />
        </div>
      </SurfaceCard>
      <SurfaceCard>
        <SectionTitle title="Proposal queue" description="The lab lane remains accessible for hypothesis review without overwhelming the live betting workspace." />
        <div className="space-y-3">
          {proposals.length ? (
            proposals.map((proposal) => (
              <div key={proposal.id} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-white">{proposal.title ?? proposal.hypothesis ?? `Proposal ${proposal.id}`}</p>
                    <p className="text-xs text-slate-500">{proposal.status ?? "pending"}</p>
                  </div>
                  <div className="rounded-full bg-fuchsia-400/12 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-fuchsia-200">
                    {proposal.expected_edge ? `${proposal.expected_edge.toFixed(1)}%` : "watch"}
                  </div>
                </div>
              </div>
            ))
          ) : (
            <EmptyState message="No research proposals are queued yet." />
          )}
        </div>
      </SurfaceCard>
    </div>
  )
}

function ComponentTable({
  title,
  components,
}: {
  title: string
  components?: Record<string, number>
}) {
  const entries = Object.entries(components ?? {})
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <h4 className="mb-3 text-sm font-semibold text-white">{title}</h4>
      {entries.length ? (
        <div className="space-y-2">
          {entries.map(([key, value]) => (
            <div key={key} className="flex items-center justify-between gap-4 text-sm">
              <span className="capitalize text-slate-400">{key.replaceAll("_", " ")}</span>
              <span className="font-medium text-slate-100">{formatNumber(value, 2)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No component detail available yet.</p>
      )}
    </div>
  )
}

function MetricsCategoryTable({
  title,
  categories,
}: {
  title: string
  categories?: Record<string, Record<string, number | string | null>>
}) {
  const entries = Object.entries(categories ?? {})
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <h4 className="mb-3 text-sm font-semibold text-white">{title}</h4>
      {entries.length ? (
        <div className="space-y-4">
          {entries.map(([category, values]) => (
            <div key={category}>
              <p className="mb-2 text-xs uppercase tracking-[0.16em] text-slate-500">{category}</p>
              <div className="grid gap-2 md:grid-cols-2">
                {Object.entries(values).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-4 rounded-xl border border-white/6 px-3 py-2 text-sm">
                    <span className="capitalize text-slate-400">{key.replaceAll("_", " ")}</span>
                    <span className="font-medium text-slate-100">{typeof value === "number" ? formatNumber(value, 2) : String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No current market metrics are available for this player.</p>
      )}
    </div>
  )
}

function LabeledInput({
  label,
  onChange,
  type = "text",
  value,
}: {
  label: string
  onChange: (value: string) => void
  type?: string
  value: string
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-500">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/30"
      />
    </label>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">{message}</div>
}

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Sparkles
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="rounded-xl bg-white/6 p-2 text-cyan-200">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <p className="truncate text-sm text-slate-100">{value}</p>
      </div>
    </div>
  )
}

function ChartColumnIcon() {
  return <div className="h-4 w-4 rounded-full bg-cyan-300/80" aria-hidden="true" />
}

function BookFilterBar({
  books,
  selectedBooks,
  onSelectedBooksChange,
}: {
  books: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
}) {
  return (
    <div className="mb-4 rounded-2xl border border-white/8 bg-black/20 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Book filter</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => onSelectedBooksChange([])}>
            All books
          </Button>
          <Button size="sm" variant="outline" onClick={() => onSelectedBooksChange(books)}>
            Select all
          </Button>
          <Button size="sm" variant="outline" onClick={() => onSelectedBooksChange([])}>
            Clear
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {books.length ? (
          books.map((book) => {
            const active = selectedBooks.includes(book)
            return (
              <button
                key={book}
                type="button"
                onClick={() => {
                  if (active) {
                    onSelectedBooksChange(selectedBooks.filter((entry) => entry !== book))
                  } else {
                    onSelectedBooksChange([...selectedBooks, book])
                  }
                }}
                className={`rounded-full border px-3 py-1 text-xs uppercase tracking-[0.16em] transition ${
                  active
                    ? "border-cyan-300/40 bg-cyan-400/15 text-cyan-100"
                    : "border-white/10 bg-white/5 text-slate-300 hover:border-white/30"
                }`}
              >
                {book}
              </button>
            )
          })
        ) : (
          <p className="text-sm text-slate-400">No sportsbook rows detected yet.</p>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {selectedBooks.length === 0
          ? "Showing all books."
          : `Showing ${selectedBooks.length} selected book${selectedBooks.length === 1 ? "" : "s"}.`}
      </p>
    </div>
  )
}

function flattenSecondaryBets(predictionRun: PredictionRunResponse | null) {
  const entries = Object.entries(predictionRun?.value_bets ?? {})
  return entries
    .flatMap(([market, bets]) =>
      bets
        .filter((bet) => bet.is_value)
        .map((bet) => ({
          market,
          player: bet.player,
          odds: bet.odds,
          ev: bet.ev,
          confidence: bet.confidence,
        })),
    )
    .sort((left, right) => right.ev - left.ev)
}

function buildMatchupKey(matchup: MatchupBet) {
  return `${matchup.pick_key}-${matchup.opponent_key}-${matchup.market_type ?? "matchup"}`
}

function secondaryBadgeLabel(market: string) {
  const normalized = market.toLowerCase()
  if (normalized.includes("miss")) {
    return "miss-cut"
  }
  if (normalized.includes("top") || normalized.includes("placement")) {
    return "placement"
  }
  return "mispriced"
}

function normalizeSportsbook(value?: string | null): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
}

function collectAvailableBooks(
  predictionRun: PredictionRunResponse | null,
  liveSnapshot: LiveRefreshSnapshot | null,
): string[] {
  const names = new Set<string>()
  for (const matchup of predictionRun?.matchup_bets ?? []) {
    const normalized = normalizeSportsbook(matchup.book)
    if (normalized) {
      names.add(normalized)
    }
  }
  for (const row of liveSnapshot?.live_tournament?.matchups ?? []) {
    const normalized = normalizeSportsbook(row.bookmaker)
    if (normalized) {
      names.add(normalized)
    }
  }
  for (const row of liveSnapshot?.upcoming_tournament?.matchups ?? []) {
    const normalized = normalizeSportsbook(row.bookmaker)
    if (normalized) {
      names.add(normalized)
    }
  }
  return Array.from(names).sort()
}

function buildHydratedPredictionRun(snapshot: LiveRefreshSnapshot | null): PredictionRunResponse | null {
  if (!snapshot) {
    return null
  }
  const source = snapshot.live_tournament ?? snapshot.upcoming_tournament
  if (!source) {
    return null
  }
  const rankings = source.rankings ?? []
  const matchups = source.matchups ?? []
  return {
    status: "hydrated",
    event_name: source.event_name ?? "Event",
    course_name: source.course_name ?? "",
    field_size: source.field_size ?? rankings.length,
    composite_results: rankings.map((row) => ({
      player_key: row.player_key ?? normalize_name_for_ui(row.player),
      player_display: row.player,
      rank: Number(row.rank ?? 0),
      composite: Number(row.composite ?? 0),
      course_fit: Number(row.course_fit ?? 0),
      form: Number(row.form ?? 0),
      momentum: Number(row.momentum ?? 0),
    })),
    matchup_bets: matchups.map((row) => {
      const pickKey = row.player_key ?? normalize_name_for_ui(row.player)
      const opponentKey = row.opponent_key ?? normalize_name_for_ui(row.opponent)
      const ev = Number(row.ev ?? 0)
      return {
        pick: row.player,
        pick_key: pickKey,
        opponent: row.opponent,
        opponent_key: opponentKey,
        odds: String(row.market_odds ?? "--"),
        book: normalizeSportsbook(row.bookmaker) || "unknown",
        model_win_prob: Number(row.model_prob ?? 0.5),
        implied_prob: 0.5,
        ev,
        ev_pct: `${(ev * 100).toFixed(1)}%`,
        composite_gap: 0,
        form_gap: 0,
        course_fit_gap: 0,
        reason: "Hydrated from always-on snapshot",
      }
    }),
    value_bets: {},
    warnings: ["Hydrated from live snapshot. Run a manual prediction for full model details."],
  }
}

function normalize_name_for_ui(value?: string): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

function isCutFinishState(finishState?: string | null) {
  if (!finishState) {
    return false
  }
  const normalized = finishState.trim().toUpperCase()
  return normalized === "CUT" || normalized === "MDF" || normalized === "WD" || normalized === "DQ" || normalized === "DNS"
}

export default App
