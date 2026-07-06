/**
 * Standalone Players Page
 * Full DataGolf-style player profiles accessible without an active tournament.
 * Route: /players
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, User, X } from "lucide-react"

import {
  PentagonRadar,
  BeeswarmStrip,
  RollingBarLine,
  ApproachArcGauges,
  HistoryTable,
} from "@/components/charts-v2"
import type { BeeswarmCategory, RollingEvent, ApproachBucket, HistoryEvent } from "@/components/charts-v2"
import { BentoPanel } from "@/components/monitoring"
import { PlayersKpiCell } from "@/components/players-kpi-cell"
import { FieldBoardPanel } from "@/components/players/field-board-panel"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { EmptyState } from "@/components/ui/empty-state"
import { ErrorState, LoadingState } from "@/components/ui/feedback-state"
import { HeroDataGrid } from "@/components/monitoring"
import { PageHeader } from "@/components/ui/page-header"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"
import type { CompositePlayer, StandalonePlayerProfile, StandaloneRecentRoundSample } from "@/lib/types"
import { computeSgTrajectoryBounds } from "@/lib/metric-heat"
import {
  PLAYER_PAGE_KPI_TOOLTIPS,
  PLAYER_PROFILE_STAT_TOOLTIPS,
  POWER_RANKINGS_HELP,
  ROLLING_WINDOW_ROW_TOOLTIP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"
import {
  buildCourseFitColumns,
  buildFieldListColumns,
  buildRecentRoundsColumns,
  buildRollingSgGridColumns,
  type CourseFitRow,
  type FieldListRow,
  type RollingSgGridRow,
} from "@/lib/players-columns"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"

type Tone = "positive" | "negative" | "neutral"

function tone(v?: number | null): Tone {
  if (v == null) return "neutral"
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"
}

function signed(v?: number | null, d = 3): string {
  if (v == null) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(d)}`
}

function heatUnitForSg(v?: number | null, maxAbs = 2.5): number {
  if (v == null) return 0.5
  return Math.min(1, Math.max(0, (v + maxAbs) / (maxAbs * 2)))
}

function MetricCard({
  label,
  value,
  tone: t = "neutral",
  sub,
  title: tip,
}: {
  label: string
  value: string | React.ReactNode
  tone?: Tone
  sub?: string
  title?: string
}) {
  return (
    <div title={tip} className={cn("profile-metric-card", tip && "profile-metric-card--help")}>
      <div className="profile-metric-label">{label}</div>
      <div className={cn("profile-metric-value", `profile-metric-value--${t}`)}>{value}</div>
      {sub ? <div className="players-kpi-sub">{sub}</div> : null}
    </div>
  )
}

function PlayerSearchSidebar({
  activePlayers,
  selectedKey,
  onSelect,
  trajectoryBounds,
}: {
  activePlayers: CompositePlayer[]
  selectedKey: string | null
  onSelect: (key: string, display: string) => void
  trajectoryBounds: { min: number; max: number }
}) {
  const [query, setQuery] = useState("")

  const searchQuery = useQuery({
    queryKey: ["player-search", query],
    queryFn: () => api.searchPlayers(query),
    enabled: query.length >= 2,
    staleTime: 30_000,
  })

  const showSearch = query.length >= 2
  const searchResults = useMemo(() => searchQuery.data?.players ?? [], [searchQuery.data])

  const filteredActive = useMemo(() => {
    if (!query) return activePlayers
    const q = query.toLowerCase()
    return activePlayers.filter(
      (p) => p.player_display.toLowerCase().includes(q) || p.player_key.includes(q),
    )
  }, [activePlayers, query])

  const activeByKey = useMemo(
    () => new Map(activePlayers.map((p) => [p.player_key, p])),
    [activePlayers],
  )

  const displayList = useMemo((): FieldListRow[] => {
    if (!showSearch) {
      return filteredActive.map((p) => ({
        key: p.player_key,
        player_key: p.player_key,
        player_display: p.player_display,
        inField: true,
        model: p,
      }))
    }
    const activeKeys = new Set(filteredActive.map((p) => p.player_key))
    const dbOnly = searchResults.filter((r) => !activeKeys.has(r.player_key))
    return [
      ...filteredActive.map((p) => ({
        player_key: p.player_key,
        player_display: p.player_display,
        inField: true,
        model: p,
      })),
      ...dbOnly.map((r) => ({
        player_key: r.player_key,
        player_display: r.player_display,
        inField: false,
        model: activeByKey.get(r.player_key),
      })),
    ]
  }, [activeByKey, filteredActive, searchResults, showSearch])

  const fieldColumns = useMemo(
    () => buildFieldListColumns({ selectedKey, onSelect, trajectoryBounds }),
    [selectedKey, onSelect, trajectoryBounds],
  )

  return (
    <div className="players-layout-sidebar">
      <div className="players-search-wrap">
        <div className="players-search-inner">
          <Search size={11} className="players-search-icon" aria-hidden />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search players…"
            data-testid="players-search"
            aria-label="Search players"
            className="players-search-input"
          />
          {query ? (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="players-search-clear"
              aria-label="Clear search"
            >
              <X size={10} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="players-sidebar-list">
        {!query && activePlayers.length > 0 ? (
          <div className="players-sidebar-section-label">Current Field</div>
        ) : null}
        {query.length >= 2 && displayList.some((d) => !d.inField) ? (
          <div className="players-sidebar-section-label">Search Results</div>
        ) : null}
        {displayList.length === 0 ? (
          <div className="players-sidebar-empty">
            {query.length >= 2 ? "No players found" : "No field loaded"}
          </div>
        ) : (
          <div className="players-field-grid-wrap" data-testid="players-field-grid">
            <HeroDataGrid
              data={displayList}
              columns={fieldColumns}
              density="compact"
              getRowId={(row) => row.player_key}
              emptyMessage="No players"
              testId="players-field-grid-inner"
            />
          </div>
        )}
      </div>
    </div>
  )
}

function PlayerProfileView({
  playerKey,
  playerDisplay,
  activePlayers,
}: {
  playerKey: string
  playerDisplay: string
  activePlayers: CompositePlayer[]
}) {
  const profileQuery = useQuery<StandalonePlayerProfile, Error>({
    queryKey: ["standalone-profile", playerKey],
    queryFn: () => api.getPlayerStandaloneProfile(playerKey),
    staleTime: 5 * 60_000,
    gcTime: 15 * 60_000,
    retry: 1,
    retryDelay: 1000,
  })

  const p = profileQuery.data
  const modelPlayer = useMemo(
    () => activePlayers.find((player) => player.player_key === playerKey),
    [activePlayers, playerKey],
  )
  const trajectoryBounds = useMemo(() => computeSgTrajectoryBounds(activePlayers), [activePlayers])

  const rollingGridRows = useMemo((): RollingSgGridRow[] => {
    if (!p?.rolling_windows_expanded) return []
    return (["10", "25", "50"] as const).map((windowKey) => ({
      window: windowKey,
      sg_total: p.rolling_windows_expanded?.sg_total?.[windowKey],
      sg_ott: p.rolling_windows_expanded?.sg_ott?.[windowKey],
      sg_app: p.rolling_windows_expanded?.sg_app?.[windowKey],
      sg_arg: p.rolling_windows_expanded?.sg_arg?.[windowKey],
      sg_putt: p.rolling_windows_expanded?.sg_putt?.[windowKey],
      sg_t2g: p.rolling_windows_expanded?.sg_t2g?.[windowKey],
    }))
  }, [p?.rolling_windows_expanded])

  const courseFitRows = useMemo(
    (): CourseFitRow[] => p?.course_summaries ?? [],
    [p?.course_summaries],
  )

  const recentRoundRows = useMemo(
    (): StandaloneRecentRoundSample[] => p?.recent_rounds_sample?.slice(0, 24) ?? [],
    [p?.recent_rounds_sample],
  )

  const rollingColumns = useMemo(() => buildRollingSgGridColumns(), [])
  const courseColumns = useMemo(() => buildCourseFitColumns(), [])
  const roundColumns = useMemo(() => buildRecentRoundsColumns(), [])

  if (profileQuery.isLoading) {
    return (
      <LoadingState
        message={`Loading ${playerDisplay}…`}
        className="players-profile-loading"
      />
    )
  }

  if (profileQuery.isError || !p) {
    return (
      <ErrorState
        message="Failed to load profile. Check that the backend is running and the player key is valid."
        className="players-profile-error"
      />
    )
  }

  const roundsOldestToNewest: StandaloneRecentRoundSample[] = [...(p.recent_rounds_sample ?? [])].reverse()
  const roundSeriesByMetric = {
    APP: roundsOldestToNewest
      .map((round) => round.sg_app)
      .filter((value): value is number => typeof value === "number"),
    ARG: roundsOldestToNewest
      .map((round) => round.sg_arg)
      .filter((value): value is number => typeof value === "number"),
    PUTT: roundsOldestToNewest
      .map((round) => round.sg_putt)
      .filter((value): value is number => typeof value === "number"),
    OTT: roundsOldestToNewest
      .map((round) => round.sg_ott)
      .filter((value): value is number => typeof value === "number"),
    T2G: roundsOldestToNewest
      .map((round) => round.sg_t2g)
      .filter((value): value is number => typeof value === "number"),
  } as const

  return (
    <div className="players-profile-scroll">
      <div className="players-profile-header">
        <div className="players-profile-header-row">
          <div>
            <div className="players-profile-eyebrow">Player Profile</div>
            <div className="players-profile-name">{p.player_display}</div>
          </div>
          <div className="players-status-pills">
            {p.has_skill_data ? <span className="status-pill good">DG Skills ✓</span> : null}
            {p.has_ranking_data ? <span className="status-pill good">Rankings ✓</span> : null}
            {p.has_approach_data ? <span className="status-pill good">Approach ✓</span> : null}
            {!p.has_skill_data && !p.has_ranking_data ? (
              <span className="status-pill warn">No live DG data</span>
            ) : null}
          </div>
        </div>

        <div className="players-kpi-grid">
          {[
            { label: "DG Rank", value: p.header.dg_rank ? `#${p.header.dg_rank}` : "—" },
            { label: "OWGR", value: p.header.owgr_rank ? `#${p.header.owgr_rank}` : "—" },
            {
              label: "DG Skill",
              value: p.header.dg_skill_estimate != null ? signed(p.header.dg_skill_estimate, 2) : "—",
              tone: tone(p.header.dg_skill_estimate),
              accentUnit:
                p.header.dg_skill_estimate != null ? heatUnitForSg(p.header.dg_skill_estimate) : undefined,
            },
            {
              label: "Total SG",
              value: p.sg_skills.sg_total != null ? signed(p.sg_skills.sg_total) : "—",
              tone: tone(p.sg_skills.sg_total),
              accentUnit: p.sg_skills.sg_total != null ? heatUnitForSg(p.sg_skills.sg_total) : undefined,
            },
            { label: "Events (DB)", value: String(p.header.events_tracked ?? 0), sub: "tracked events" },
            { label: "Rounds (DB)", value: String(p.header.rounds_in_db ?? 0), sub: "stored rounds" },
          ].map((item, i, arr) => (
            <div
              key={item.label}
              className={cn("players-kpi-cell-wrap", i === arr.length - 1 && "players-kpi-cell-wrap--last")}
            >
              <PlayersKpiCell {...item} title={PLAYER_PAGE_KPI_TOOLTIPS[item.label]} />
            </div>
          ))}
        </div>
      </div>

      <div className="players-content">
        {modelPlayer ? (
          <CollapsibleSection
            title="Model alignment"
            description="Current field model context"
            defaultOpen
          >
            <div className="profile-panel-body profile-panel-body--grid-5">
              <MetricCard
                label="Model Rank"
                value={`#${modelPlayer.rank}`}
                title={PLAYER_PROFILE_STAT_TOOLTIPS["Model Rank"]}
              />
              <MetricCard
                label="Composite"
                value={modelPlayer.composite.toFixed(1)}
                title={PLAYER_PROFILE_STAT_TOOLTIPS.Composite}
              />
              <MetricCard
                label="Form"
                value={modelPlayer.form.toFixed(1)}
                title={PLAYER_PROFILE_STAT_TOOLTIPS.Form}
              />
              <MetricCard
                label="Course Fit"
                value={modelPlayer.course_fit.toFixed(1)}
                title={PLAYER_PROFILE_STAT_TOOLTIPS["Course Fit"]}
              />
              <div title={SG_TRAJECTORY_HELP} className="profile-metric-card profile-metric-card--help">
                <div className="profile-metric-label">SG Trajectory</div>
                <SgTrajectoryMeter
                  momentumTrend={modelPlayer.momentum_trend}
                  momentumDirection={modelPlayer.momentum_direction}
                  normMin={trajectoryBounds.min}
                  normMax={trajectoryBounds.max}
                />
              </div>
            </div>
          </CollapsibleSection>
        ) : null}

        {p.ranking_card ? (
          <CollapsibleSection title="DG identity" description="Structured DataGolf ranking context">
            <div className="profile-panel-body profile-panel-body--grid-4">
              <MetricCard
                label="DG Rank"
                value={p.ranking_card.dg_rank ? `#${p.ranking_card.dg_rank}` : "—"}
                title={PLAYER_PROFILE_STAT_TOOLTIPS["DG Rank"]}
              />
              <MetricCard
                label="OWGR"
                value={p.ranking_card.owgr_rank ? `#${p.ranking_card.owgr_rank}` : "—"}
                title={PLAYER_PROFILE_STAT_TOOLTIPS.OWGR}
              />
              <MetricCard
                label="DG Skill"
                value={signed(p.ranking_card.dg_skill_estimate, 2)}
                tone={tone(p.ranking_card.dg_skill_estimate)}
                title={PLAYER_PROFILE_STAT_TOOLTIPS["DG Skill"]}
              />
              <MetricCard
                label="Primary Tour"
                value={p.ranking_card.primary_tour ?? "—"}
                title={PLAYER_PROFILE_STAT_TOOLTIPS["Primary Tour"]}
              />
            </div>
          </CollapsibleSection>
        ) : null}

        <CollapsibleSection title="Skill profile" description="Radar, driving stats, rolling windows" defaultOpen>
          <div className="profile-skill-radar-inner">
            <div className="profile-panel-body profile-panel-body--chart">
              <PentagonRadar skills={p.sg_skills} playerName={p.player_display} height={300} />
            </div>
            <div className="profile-skill-side">
              <div className="profile-section-label">Driving</div>
              <div className="profile-skill-metrics-2">
                <MetricCard
                  label="Distance"
                  value={p.sg_skills.driving_dist ? `${p.sg_skills.driving_dist.toFixed(0)} yd` : "—"}
                  title={PLAYER_PROFILE_STAT_TOOLTIPS.Distance}
                />
                <MetricCard
                  label="Accuracy"
                  value={
                    p.sg_skills.driving_acc
                      ? `${(p.sg_skills.driving_acc * 100).toFixed(1)}%`
                      : "—"
                  }
                  title={PLAYER_PROFILE_STAT_TOOLTIPS.Accuracy}
                />
              </div>
              <div className="profile-section-label profile-section-label-spaced">Rolling windows</div>
              {(["10", "25", "50"] as const).map((w) => {
                const val = p.rolling_windows?.[w]
                const t = tone(val)
                return (
                  <div key={w} title={ROLLING_WINDOW_ROW_TOOLTIP} className="profile-rolling-row">
                    <span className="profile-rolling-label">L{w}</span>
                    <span className={cn("profile-rolling-value", `profile-metric-value--${t}`)}>
                      {val != null ? signed(val) : "—"}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="Field distribution" description="You (green ring) vs field (grey)">
          <div className="profile-panel-body profile-panel-body--chart">
            <BeeswarmStrip
              categories={[
                { label: "Total SG", shortLabel: "TOTAL", playerValue: p.sg_skills.sg_total },
                { label: "Approach", shortLabel: "APP", playerValue: p.sg_skills.sg_app },
                { label: "Around Green", shortLabel: "ARG", playerValue: p.sg_skills.sg_arg },
                { label: "Putting", shortLabel: "PUTT", playerValue: p.sg_skills.sg_putt },
                { label: "Off the Tee", shortLabel: "OTT", playerValue: p.sg_skills.sg_ott },
              ] satisfies BeeswarmCategory[]}
              height={300}
            />
          </div>
        </CollapsibleSection>

        {rollingGridRows.length > 0 ? (
          <CollapsibleSection title="Rolling windows grid" description="L10 / L25 / L50 by SG category">
            <div className="profile-panel-body profile-panel-body--scroll" data-testid="players-profile-rolling-windows">
              <HeroDataGrid
                data={rollingGridRows}
                columns={rollingColumns}
                density="compact"
                getRowId={(row) => row.window}
                testId="players-profile-rolling-windows-grid"
              />
            </div>
          </CollapsibleSection>
        ) : null}

        {p.recent_events.length > 0 ? (
          <CollapsibleSection title="Event form" description="Per-event SG bars + moving average">
            <div className="profile-panel-body">
              <RollingBarLine
                events={p.recent_events as RollingEvent[]}
                height={180}
                maWindow={5}
                trendSeries={p.trend_series}
                roundSeriesByMetric={roundSeriesByMetric}
              />
            </div>
          </CollapsibleSection>
        ) : null}

        {courseFitRows.length > 0 ? (
          <CollapsibleSection title="Course rollups" description="Most tracked courses by rounds played">
            <div className="profile-panel-body profile-panel-body--scroll" data-testid="players-profile-course-rollups">
              <HeroDataGrid
                data={courseFitRows}
                columns={courseColumns}
                density="compact"
                getRowId={(row) => row.course_name}
                testId="players-profile-course-rollups-grid"
              />
            </div>
          </CollapsibleSection>
        ) : null}

        {recentRoundRows.length > 0 ? (
          <CollapsibleSection title="Round log" description="Recent rounds with SG splits">
            <div className="profile-panel-body profile-panel-body--scroll" data-testid="players-profile-round-log">
              <HeroDataGrid
                data={recentRoundRows}
                columns={roundColumns}
                density="compact"
                getRowId={(row) =>
                  `${row.event_completed ?? "na"}-${row.round_num ?? "r"}-${row.event_name ?? ""}`
                }
                testId="players-profile-round-log-grid"
              />
            </div>
          </CollapsibleSection>
        ) : null}

        {p.approach_buckets.length > 0
          ? (() => {
              const bucketMap: Record<string, { fw?: number; rgh?: number }> = {}
              for (const b of p.approach_buckets) {
                const isFw =
                  b.label.toLowerCase().includes("fw") || b.key.toLowerCase().includes("_fw")
                const range = b.label.replace(/ ?FW| ?Rgh| ?Rough/gi, "").trim()
                if (!bucketMap[range]) bucketMap[range] = {}
                if (isFw) bucketMap[range].fw = b.value
                else bucketMap[range].rgh = b.value
              }
              const arcBuckets: ApproachBucket[] = Object.entries(bucketMap)
                .filter(([, v]) => v.fw != null || v.rgh != null)
                .map(([label, v]) => ({ label, fw_sg: v.fw ?? 0, rgh_sg: v.rgh ?? 0 }))

              if (!arcBuckets.length) return null
              return (
                <BentoPanel title="Approach by Distance" span={12} testId="players-profile-approach-panel">
                  <p className="panel-label-dim mb-3 block">
                    Semicircle arc per yardage bucket. Tick marks show tour average.
                  </p>
                  <div className="profile-panel-card-body">
                    <ApproachArcGauges buckets={arcBuckets} />
                  </div>
                </BentoPanel>
              )
            })()
          : null}

        {p.recent_events.length > 0 ? (
          <BentoPanel title="Tournament History" span={12} testId="players-profile-history-panel">
            <p className="panel-label-dim mb-3 block">
              Win = gold. Top 10 = green. MC = red. Inline bars show SG by category.
            </p>
            <div className="profile-panel-card-body">
              <HistoryTable events={p.recent_events as HistoryEvent[]} maxRows={16} />
            </div>
          </BentoPanel>
        ) : null}

        {!p.has_skill_data && !p.has_ranking_data && !p.has_approach_data && p.recent_events.length === 0 ? (
          <div className="profile-empty-center">
            <div className="profile-empty-msg">No data available for this player</div>
            <div className="players-sidebar-empty">
              Ensure DATAGOLF_API_KEY is set and round data has been backfilled.
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function PlayersEmptyPrompt() {
  return (
    <EmptyState
      message="Select a player from the list"
      description="View full skill profile, rolling windows, and course history."
      icon={<User size={24} className="profile-empty-icon" />}
      className="profile-empty-center"
    />
  )
}

export function PlayersPage({
  players,
  initialPlayerKey,
}: {
  players: CompositePlayer[]
  initialPlayerKey?: string | null
  selectedPlayerProfile?: unknown
  onPlayerSelect?: (key: string) => void
  richProfilesEnabled?: boolean
}) {
  const initialFromUrl =
    initialPlayerKey ??
    (typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("player")
      : null)
  const [selectedKey, setSelectedKey] = useState<string | null>(initialFromUrl)
  const [selectedDisplay, setSelectedDisplay] = useState<string>("")
  const trajectoryBounds = useMemo(() => computeSgTrajectoryBounds(players), [players])

  const handleSelect = useCallback((key: string, display: string) => {
    setSelectedKey(key)
    setSelectedDisplay(display)
  }, [])

  const first = players[0]
  const effectiveKey = selectedKey ?? first?.player_key ?? null
  const fallbackSelectedDisplay = selectedKey
    ? (players.find((player) => player.player_key === selectedKey)?.player_display ??
      selectedKey.replaceAll("_", " "))
    : ""
  const effectiveDisplay = selectedKey
    ? selectedDisplay || fallbackSelectedDisplay
    : (first?.player_display ?? "")

  useEffect(() => {
    if (!effectiveKey || typeof window === "undefined") return
    const url = new URL(window.location.href)
    url.searchParams.set("player", effectiveKey)
    window.history.replaceState({}, "", url.toString())
  }, [effectiveKey])

  return (
    <div
      className="monitor-research-page monitor-scroll-region product-page--satellite"
      data-testid="players-page"
    >
      <div className="px-5 pt-5">
        <PageHeader
          eyebrow="Field intelligence"
          title="Players"
          description="Deep-dive standalone profiles with field-board context and theme-aware charts."
        />
      </div>
      <div className="px-5 pb-4 pt-4">
        <FieldBoardPanel onSelect={handleSelect} />
      </div>
      <div className="px-5 pb-5">
        <div className="players-layout players-layout--full-width">
          <PlayerSearchSidebar
            activePlayers={players}
            selectedKey={effectiveKey}
            onSelect={handleSelect}
            trajectoryBounds={trajectoryBounds}
          />

          <div className="players-layout-main">
            {effectiveKey ? (
              <PlayerProfileView
                key={effectiveKey}
                playerKey={effectiveKey}
                playerDisplay={effectiveDisplay}
                activePlayers={players}
              />
            ) : (
              <PlayersEmptyPrompt />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
