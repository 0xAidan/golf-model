import { useEffect, useMemo, useRef } from "react"
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
  MatchupBet,
  PlayerProfile,
  PredictionRunRequest,
  PredictionRunResponse,
  ResearchProposal,
  SecondaryBet,
  ScheduleEvent,
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
  const [predictionRequest, setPredictionRequest] = useLocalStorageState<PredictionRunRequest>("golf-model.prediction-request", DEFAULT_REQUEST)
  const [storedPredictionRun, setStoredPredictionRun] = useLocalStorageState<PredictionRunResponse | null>("golf-model.latest-prediction-run", null)
  const [matchupSearch, setMatchupSearch] = useLocalStorageState("golf-model.matchup-search", "")
  const [minEdge, setMinEdge] = useLocalStorageState("golf-model.min-edge", 0.02)
  const [predictionLayout, setPredictionLayout] = useLocalStorageState<"board" | "table" | "players">("golf-model.prediction-layout", "board")
  const [selectedPlayerKey, setSelectedPlayerKey] = useLocalStorageState("golf-model.selected-player", "")
  const [selectedMatchupKey, setSelectedMatchupKey] = useLocalStorageState("golf-model.selected-matchup", "")
  const predictionRun = useMemo(() => normalizePredictionRun(storedPredictionRun), [storedPredictionRun])

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
  const scheduleQuery = useQuery({
    queryKey: ["schedule-events", predictionRequest.tour],
    queryFn: () => api.getScheduleEvents(predictionRequest.tour),
  })
  const playerProfileQuery = useQuery({
    queryKey: ["player-profile", selectedPlayerKey, predictionRun?.tournament_id, predictionRun?.course_num],
    queryFn: () => api.getPlayerProfile(selectedPlayerKey, predictionRun?.tournament_id ?? 0, predictionRun?.course_num),
    enabled: Boolean(selectedPlayerKey && predictionRun?.tournament_id),
  })
  const selectedPlayerProfile = useMemo(() => normalizePlayerProfile(playerProfileQuery.data), [playerProfileQuery.data])

  const predictionMutation = useMutation({
    mutationFn: api.runPrediction,
    onSuccess: (result) => {
      setStoredPredictionRun(normalizePredictionRun(result))
      if (result.composite_results?.[0]?.player_key) {
        setSelectedPlayerKey(result.composite_results[0].player_key)
      }
      if (result.matchup_bets?.[0]) {
        setSelectedMatchupKey(buildMatchupKey(result.matchup_bets[0]))
      }
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
    },
  })

  const gradeMutation = useMutation({
    mutationFn: () => api.gradeLatestTournament(dashboardQuery.data?.latest_completed_event ?? undefined),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
    },
  })

  const players = predictionRun?.composite_results ?? []
  const filteredMatchups = useMemo(() => {
    const sourceMatchups = predictionRun?.matchup_bets ?? []
    return sourceMatchups.filter((matchup) => {
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesSearch && matchup.ev >= minEdge
    })
  }, [matchupSearch, minEdge, predictionRun?.matchup_bets])

  const selectedPlayer = players.find((player) => player.player_key === selectedPlayerKey) ?? players[0] ?? null
  const selectedMatchup =
    filteredMatchups.find((matchup) => buildMatchupKey(matchup) === selectedMatchupKey) ??
    filteredMatchups[0] ??
    null

  const secondaryBets = flattenSecondaryBets(predictionRun)
  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const proposals = researchQuery.data ?? []
  const dashboard = dashboardQuery.data as DashboardState | undefined
  const scheduleEvents = useMemo(() => scheduleQuery.data?.events ?? [], [scheduleQuery.data?.events])
  const selectedScheduleEvent =
    scheduleEvents.find((event) => event.event_name === predictionRequest.tournament) ??
    scheduleEvents[0] ??
    null
  const tournamentOptions = scheduleEvents.length
    ? scheduleEvents.map((event) => ({
        value: event.event_name,
        label: buildEventOptionLabel(event),
      }))
    : predictionRequest.tournament
      ? [{ value: predictionRequest.tournament, label: predictionRequest.tournament }]
      : []
  const courseOptions = selectedScheduleEvent?.course
    ? [{ value: selectedScheduleEvent.course, label: selectedScheduleEvent.course }]
    : predictionRequest.course
      ? [{ value: predictionRequest.course, label: predictionRequest.course }]
      : []
  const scheduleStatusMessage = scheduleQuery.isLoading
    ? "Loading tournament schedule..."
    : scheduleQuery.isError
      ? "Could not load tournament schedule. Check your DataGolf API key and backend logs."
      : !scheduleEvents.length
        ? "No schedule events returned for this tour."
        : null

  useEffect(() => {
    if (!scheduleEvents.length) {
      return
    }

    const nextTournament = selectedScheduleEvent?.event_name ?? ""
    const nextCourse = selectedScheduleEvent?.course ?? ""
    const shouldUpdateTournament = predictionRequest.tournament !== nextTournament
    const shouldUpdateCourse = predictionRequest.course !== nextCourse

    if (!shouldUpdateTournament && !shouldUpdateCourse) {
      return
    }

    setPredictionRequest({
      ...predictionRequest,
      tournament: nextTournament,
      course: nextCourse,
    })
  }, [
    predictionRequest,
    predictionRequest.course,
    predictionRequest.enable_ai,
    predictionRequest.tournament,
    predictionRequest.mode,
    predictionRequest.tour,
    scheduleEvents,
    selectedScheduleEvent,
    setPredictionRequest,
  ])

  return (
    <CommandShell
      headline={predictionRun?.event_name ?? "Operator command station"}
      subheadline="Desktop-first betting intelligence across predictions, player drill-downs, course context, grading continuity, and research control."
      actions={
        <>
          <Button
            size="lg"
            onClick={() => predictionMutation.mutate(predictionRequest)}
            disabled={predictionMutation.isPending}
          >
            {predictionMutation.isPending ? "Running prediction..." : "Run prediction"}
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => gradeMutation.mutate()}
            disabled={gradeMutation.isPending}
          >
            {gradeMutation.isPending ? "Grading..." : "Grade latest event"}
          </Button>
        </>
      }
    >
      <SurfaceCard className="mb-6">
        <SectionTitle
          title="Run controls"
          description="Prediction runs stay quantitative. This shell only changes how you inspect, filter, and revisit the output."
        />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <LabeledInput
            label="Tour"
            value={predictionRequest.tour}
            onChange={(value) =>
              setPredictionRequest({
                ...predictionRequest,
                tour: value,
                tournament: "",
                course: "",
              })
            }
            asSelect
            options={[
              { value: "pga", label: "PGA" },
              { value: "euro", label: "DP World Tour" },
              { value: "liv", label: "LIV" },
            ]}
          />
          <LabeledInput
            label="Tournament"
            value={predictionRequest.tournament ?? ""}
            onChange={(value) => {
              const event = scheduleEvents.find((item) => item.event_name === value)
              setPredictionRequest({
                ...predictionRequest,
                tournament: value,
                course: event?.course ?? "",
              })
            }}
            asSelect
            options={tournamentOptions}
            disabled={scheduleQuery.isLoading || scheduleQuery.isError || !tournamentOptions.length}
            emptyLabel={scheduleQuery.isLoading ? "Loading tournaments..." : "No tournaments available"}
          />
          <LabeledInput
            label="Course"
            value={predictionRequest.course ?? ""}
            onChange={(value) => setPredictionRequest({ ...predictionRequest, course: value })}
            asSelect
            options={courseOptions}
            disabled={scheduleQuery.isLoading || !courseOptions.length}
            emptyLabel={scheduleQuery.isLoading ? "Loading course..." : "Select a tournament first"}
          />
          <LabeledSelect
            label="Mode"
            value={predictionRequest.mode}
            options={[
              { value: "full", label: "Full board" },
              { value: "matchups-only", label: "Matchups only" },
              { value: "placements-only", label: "Placements only" },
              { value: "round-matchups", label: "Round matchups" },
            ]}
            onChange={(value) => setPredictionRequest({ ...predictionRequest, mode: value as PredictionRunRequest["mode"] })}
          />
          <LabeledSelect
            label="AI"
            value={predictionRequest.enable_ai ? "enabled" : "disabled"}
            options={[
              { value: "enabled", label: "Enabled" },
              { value: "disabled", label: "Disabled" },
            ]}
            onChange={(value) => setPredictionRequest({ ...predictionRequest, enable_ai: value === "enabled" })}
          />
        </div>
        {scheduleStatusMessage ? (
          <p className="mt-4 rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-slate-300">
            {scheduleStatusMessage}
          </p>
        ) : null}
      </SurfaceCard>

      <Routes>
        <Route
          path="/"
          element={
            <PredictionWorkspacePage
              dashboard={dashboard}
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
              predictionRun={predictionRun}
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
              selectedPlayerProfile={selectedPlayerProfile}
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
              predictionRun={predictionRun}
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
  secondaryBets: Array<{
    market: string
    player: string
    betType: string
    odds: string
    book?: string
    ev: number
    evPct?: string
    confidence?: string
    reasoning?: string
    modelProb?: number
    marketProb?: number
  }>
  selectedPlayer: CompositePlayer | null
  selectedMatchup: MatchupBet | null
}) {
  const totalProfit = gradingHistory.reduce((sum, tournament) => sum + Number(tournament.total_profit ?? 0), 0)

  return (
    <div className="space-y-6">
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
              {filteredMatchups.map((matchup) => (
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
              ))}
            </div>
          ) : layout === "table" ? (
            <div className="overflow-hidden rounded-2xl border border-white/10">
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
            </div>
          ) : (
            <div className="grid gap-3">
              {players.slice(0, 12).map((player) => (
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
              ))}
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
            {players.slice(0, 12).map((player) => (
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
            ))}
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
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-cyan-200">
                        {formatBetTypeLabel(bet.betType)}
                      </p>
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
                      <p className="text-sm text-cyan-200">{bet.evPct ?? `${formatNumber(bet.ev * 100, 1)}% EV`}</p>
                      <p className="text-xs text-slate-300">
                        {bet.odds}
                        {bet.book ? ` @ ${bet.book}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-400">
                    <div>
                      <span className="text-slate-500">Model</span>{" "}
                      <span className="text-slate-200">
                        {bet.modelProb !== undefined ? `${formatNumber(bet.modelProb * 100, 1)}%` : "--"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Market</span>{" "}
                      <span className="text-slate-200">
                        {bet.marketProb !== undefined ? `${formatNumber(bet.marketProb * 100, 1)}%` : "--"}
                      </span>
                    </div>
                  </div>
                  {bet.reasoning ? <p className="mt-3 text-xs leading-5 text-slate-400">{bet.reasoning}</p> : null}
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
  const profileRef = useRef<HTMLDivElement | null>(null)
  const momentumValues =
    selectedPlayerProfile?.recent_rounds.map((round) => Number(round.sg_total ?? 0)).reverse() ??
    (selectedPlayer
      ? [
          selectedPlayer.course_fit,
          selectedPlayer.form,
          selectedPlayer.momentum,
          selectedPlayer.composite,
        ]
      : [])
  const courseValues = selectedPlayerProfile?.course_history.map((round) => Number(round.sg_total ?? 0)).reverse() ?? []
  const handlePlayerSelect = (playerKey: string) => {
    onPlayerSelect(playerKey)

    if (typeof window === "undefined") {
      return
    }

    if (!window.matchMedia("(max-width: 1535px)").matches) {
      return
    }

    window.requestAnimationFrame(() => {
      profileRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    })
  }

  return (
    <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
      <SurfaceCard className="self-start">
        <SectionTitle title="Projection ladder" description="Click any player to open a richer projection profile with score components and momentum context." />
        <div className="max-h-[68vh] space-y-2 overflow-y-auto pr-2">
          {players.map((player) => (
            <button
              key={player.player_key}
              type="button"
              aria-pressed={player.player_key === selectedPlayer?.player_key}
              className={
                player.player_key === selectedPlayer?.player_key
                  ? "flex w-full items-center justify-between rounded-2xl border border-cyan-300/35 bg-cyan-400/10 px-4 py-3 text-left transition"
                  : "flex w-full items-center justify-between rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-left transition hover:border-cyan-400/25 hover:bg-white/5"
              }
              onClick={() => handlePlayerSelect(player.player_key)}
            >
              <div>
                <p className="font-medium text-white">{player.player_display}</p>
                <p className="text-xs text-slate-500">rank #{player.rank}</p>
              </div>
              <p className="text-sm font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</p>
            </button>
          ))}
        </div>
      </SurfaceCard>
      <SurfaceCard className="self-start">
        <div ref={profileRef}>
          <SectionTitle
            title={selectedPlayer ? `Player profile: ${selectedPlayer.player_display}` : "Player profile"}
            description="Current-week projection context, momentum, course confidence, and sub-score detail."
          />
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
        </div>
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
          {matchups.map((matchup) => (
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
          ))}
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
  if (!entries.length) {
    return null
  }
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <h4 className="mb-3 text-sm font-semibold text-white">{title}</h4>
      <div className="space-y-2">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-4 text-sm">
            <span className="capitalize text-slate-400">{key.replaceAll("_", " ")}</span>
            <span className="font-medium text-slate-100">{formatNumber(value, 2)}</span>
          </div>
        ))}
      </div>
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
  if (!entries.length) {
    return null
  }
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <h4 className="mb-3 text-sm font-semibold text-white">{title}</h4>
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
    </div>
  )
}

function LabeledInput({
  asSelect = false,
  disabled = false,
  emptyLabel = "No options available",
  label,
  onChange,
  options = [],
  type = "text",
  value,
}: {
  asSelect?: boolean
  disabled?: boolean
  emptyLabel?: string
  label: string
  onChange: (value: string) => void
  options?: Array<{ value: string; label: string }>
  type?: string
  value: string
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-500">{label}</span>
      {asSelect ? (
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {!options.length ? (
            <option value="">{emptyLabel}</option>
          ) : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/30"
        />
      )}
    </label>
  )
}

function LabeledSelect({
  label,
  onChange,
  options,
  value,
}: {
  label: string
  onChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  value: string
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-white/10 bg-black/25 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/30"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
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

function flattenSecondaryBets(predictionRun: PredictionRunResponse | null) {
  const entries = Object.entries(predictionRun?.value_bets ?? {})
  return entries
    .flatMap(([market, bets]) =>
      asArray(bets)
        .filter((bet) => bet.is_value)
        .map((bet) => ({
          market,
          player: bet.player_display ?? bet.player,
          betType: bet.bet_type ?? market,
          odds:
            bet.best_odds !== undefined
              ? formatAmericanOdds(bet.best_odds)
              : bet.odds,
          book: bet.best_book,
          ev: bet.ev,
          evPct: bet.ev_pct,
          confidence: bet.confidence,
          reasoning: bet.reasoning,
          modelProb: bet.model_prob,
          marketProb: bet.market_prob,
        })),
    )
    .sort((left, right) => right.ev - left.ev)
}

function buildMatchupKey(matchup: MatchupBet) {
  return `${matchup.pick_key}-${matchup.opponent_key}-${matchup.market_type ?? "matchup"}`
}

function buildEventOptionLabel(event: ScheduleEvent) {
  const dateLabel = event.start_date ? ` (${event.start_date})` : ""
  return `${event.event_name}${dateLabel}`
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

function formatBetTypeLabel(betType?: string) {
  if (!betType) {
    return "Market"
  }
  const normalized = betType.replaceAll("_", " ")
  return normalized
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function formatAmericanOdds(value: number) {
  return value > 0 ? `+${value}` : String(value)
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : []
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function normalizeValueBets(valueBets: PredictionRunResponse["value_bets"]): Record<string, SecondaryBet[]> {
  if (!isRecord(valueBets)) {
    return {}
  }

  return Object.fromEntries(
    Object.entries(valueBets).map(([market, bets]) => [market, asArray(bets as SecondaryBet[])]),
  )
}

function normalizePredictionRun(predictionRun: PredictionRunResponse | null): PredictionRunResponse | null {
  if (!predictionRun) {
    return null
  }

  const fieldValidation = predictionRun.field_validation

  return {
    ...predictionRun,
    composite_results: asArray(predictionRun.composite_results),
    matchup_bets: asArray(predictionRun.matchup_bets),
    value_bets: normalizeValueBets(predictionRun.value_bets),
    warnings: asArray(predictionRun.warnings),
    errors: asArray(predictionRun.errors),
    field_validation: fieldValidation
      ? {
          ...fieldValidation,
          players_with_thin_rounds: asArray(fieldValidation.players_with_thin_rounds),
          players_missing_dg_skill: asArray(fieldValidation.players_missing_dg_skill),
        }
      : undefined,
  }
}

function normalizePlayerProfile(profile?: PlayerProfile): PlayerProfile | undefined {
  if (!profile) {
    return undefined
  }

  return {
    ...profile,
    current_metrics: isRecord(profile.current_metrics) ? (profile.current_metrics as PlayerProfile["current_metrics"]) : {},
    recent_rounds: asArray(profile.recent_rounds),
    course_history: asArray(profile.course_history),
    linked_bets: asArray(profile.linked_bets),
  }
}

export default App
