/**
 * Standalone Players Page
 * Full DataGolf-style player profiles accessible without an active tournament.
 * Route: /players
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, User, ChevronRight, X } from "lucide-react"

import {
  PentagonRadar,
  BeeswarmStrip,
  RollingBarLine,
  ApproachArcGauges,
  HistoryTable,
} from "@/components/charts-v2"
import type { BeeswarmCategory, RollingEvent, ApproachBucket, HistoryEvent } from "@/components/charts-v2"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { cn } from "@/lib/utils"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import { api } from "@/lib/api"
import type { CompositePlayer, StandalonePlayerProfile, StandaloneRecentRoundSample } from "@/lib/types"
import { computeSgTrajectoryBounds, heatSpectrumFromUnit, heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"
import {
  PLAYER_PAGE_KPI_TOOLTIPS,
  PLAYER_PROFILE_STAT_TOOLTIPS,
  POWER_RANKINGS_HELP,
  ROLLING_SG_GRID_HEADER_TOOLTIPS,
  ROLLING_WINDOW_ROW_TOOLTIP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"

/* ── Tokens ─────────────────────────────────────────────────────────── */
const VAR = {
  bg:       "var(--bg)",
  bg1:      "var(--bg-1)",
  bg2:      "var(--bg-2)",
  surface:  "var(--surface)",
  surface2: "var(--surface-2)",
  border:   "var(--border)",
  divider:  "var(--divider)",
  text:     "var(--text)",
  muted:    "var(--text-muted)",
  faint:    "var(--text-faint)",
  green:    "var(--green)",
  cyan:     "var(--cyan)",
  gold:     "var(--gold)",
  red:      "var(--red)",
  mono:     "var(--font-mono)",
}

/* ── Helpers ─────────────────────────────────────────────────────────── */
type Tone = "positive" | "negative" | "neutral"

function tone(v?: number | null): Tone {
  if (v == null) return "neutral"
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"
}

function toneColor(t: Tone) {
  return t === "positive" ? VAR.green : t === "negative" ? VAR.red : VAR.muted
}

function signed(v?: number | null, d = 3): string {
  if (v == null) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(d)}`
}

function heatUnitForSg(v?: number | null, maxAbs = 2.5): number {
  if (v == null) return 0.5
  return Math.min(1, Math.max(0, (v + maxAbs) / (maxAbs * 2)))
}

function formatCompactScore(v?: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—"
  return v.toFixed(1)
}

/* ── KPI Cell ─────────────────────────────────────────────────────────── */
function KpiCell({
  label,
  value,
  tone: t = "neutral",
  sub,
  large = false,
  accentUnit,
  title,
}: {
  label: string
  value: string | React.ReactNode
  tone?: Tone
  sub?: string
  large?: boolean
  accentUnit?: number
  /** Native tooltip (metric definition). */
  title?: string
}) {
  return (
    <div
      title={title}
      className={cn("players-kpi-cell", title && "players-kpi-cell--help")}
      style={accentUnit != null ? { background: heatSpectrumGradientAlongUnit(accentUnit, "ltr") } : undefined}
    >
      <span className={cn("players-kpi-label", accentUnit != null && "players-kpi-label--on-heat")}>{label}</span>
      <span
        className={cn(
          "players-kpi-value",
          large && "players-kpi-value--lg",
          accentUnit == null && `players-kpi-value--${t}`,
        )}
        style={accentUnit != null ? { color: "var(--bg)" } : undefined}
      >
        {value}
      </span>
      {sub && (
        <span className={cn("players-kpi-sub", accentUnit != null && "players-kpi-label--on-heat")}>{sub}</span>
      )}
    </div>
  )
}

/* ── Stat metric card ─────────────────────────────────────────────────── */
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
      {sub && <div className="players-kpi-sub">{sub}</div>}
    </div>
  )
}

/* ── Player Search Sidebar ────────────────────────────────────────────── */
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
  const [searchFocused, setSearchFocused] = useState(false)

  const searchQuery = useQuery({
    queryKey: ["player-search", query],
    queryFn: () => api.searchPlayers(query),
    enabled: query.length >= 2,
    staleTime: 30_000,
  })

  // Show active field players first, then DB search results
  const showSearch = query.length >= 2
  // Wrap in useMemo so referential identity is stable when data is unchanged —
  // prevents the displayList useMemo below from re-running on every render.
  const searchResults = useMemo(() => searchQuery.data?.players ?? [], [searchQuery.data])

  // Active field players filtered by query
  const filteredActive = useMemo(() => {
    if (!query) return activePlayers
    const q = query.toLowerCase()
    return activePlayers.filter(
      (p) => p.player_display.toLowerCase().includes(q) || p.player_key.includes(q),
    )
  }, [activePlayers, query])

  // Merge: active field + DB results (deduplicated)
  const activeByKey = useMemo(
    () => new Map(activePlayers.map((p) => [p.player_key, p])),
    [activePlayers],
  )
  const displayList = useMemo(() => {
    if (!showSearch) return filteredActive.map((p) => ({ key: p.player_key, display: p.player_display, inField: true, model: p }))
    const activeKeys = new Set(filteredActive.map((p) => p.player_key))
    const dbOnly = searchResults.filter((r) => !activeKeys.has(r.player_key))
    return [
      ...filteredActive.map((p) => ({ key: p.player_key, display: p.player_display, inField: true, model: p })),
      ...dbOnly.map((r) => ({ key: r.player_key, display: r.player_display, inField: false, model: activeByKey.get(r.player_key) })),
    ]
  }, [activeByKey, filteredActive, searchResults, showSearch])

  return (
    <div className="players-layout-sidebar">
      {/* Search input */}
      <div style={{ padding: "8px 8px 6px", borderBottom: `1px solid ${VAR.border}`, flexShrink: 0 }}>
        <div style={{ position: "relative" }}>
          <Search
            size={11}
            style={{
              position: "absolute",
              left: 8,
              top: "50%",
              transform: "translateY(-50%)",
              color: VAR.faint,
              pointerEvents: "none",
            }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="Search players…"
            data-testid="players-search"
            aria-label="Search players"
            className="players-search-input"
            style={{
              width: "100%",
              background: VAR.surface,
              border: `1px solid ${searchFocused ? "var(--border-hi)" : VAR.border}`,
              borderRadius: "var(--r-sm)",
              color: VAR.text,
              fontFamily: VAR.mono,
              fontSize: 10,
              padding: "5px 28px 5px 24px",
              outline: "none",
              transition: "border-color 120ms",
            }}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              style={{
                position: "absolute",
                right: 6,
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                color: VAR.faint,
                cursor: "pointer",
                padding: 0,
                display: "flex",
                alignItems: "center",
              }}
            >
              <X size={10} />
            </button>
          )}
        </div>
      </div>

      {/* Player list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {!query && activePlayers.length > 0 && (
          <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, padding: "4px 10px 2px" }}>
            Current Field
          </div>
        )}
        {query.length >= 2 && displayList.some((d) => !d.inField) && (
          <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, padding: "4px 10px 2px" }}>
            Search Results
          </div>
        )}
        {displayList.length === 0 && (
          <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, padding: "12px 10px", textAlign: "center" }}>
            {query.length >= 2 ? "No players found" : "No field loaded"}
          </div>
        )}
        {displayList.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => onSelect(p.key, p.display)}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "6px 10px",
              background: selectedKey === p.key ? "var(--surface-2)" : "none",
              boxShadow: selectedKey === p.key ? "inset 3px 0 0 0 var(--accent-positive)" : "none",
              border: "none",
              borderBottom: `1px solid ${VAR.divider}`,
              cursor: "pointer",
              textAlign: "left",
              gap: 4,
              transition: "background 100ms",
            }}
          >
            <div style={{ minWidth: 0, flex: 1 }}>
              <div
                style={{
                  fontFamily: VAR.mono,
                  fontSize: 11,
                  fontWeight: selectedKey === p.key ? 700 : 500,
                  color: selectedKey === p.key ? VAR.text : VAR.text,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {p.display}
              </div>
              {!p.inField && (
                <div style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.faint, marginTop: 1 }}>DB record</div>
              )}
              {p.inField && p.model && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                  <span style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.faint }} title={POWER_RANKINGS_HELP.rank}>
                    #{p.model.rank}
                  </span>
                  <span style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.cyan }} title={POWER_RANKINGS_HELP.composite}>
                    C {formatCompactScore(p.model.composite)}
                  </span>
                  <span style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.green }} title={POWER_RANKINGS_HELP.form}>
                    F {formatCompactScore(p.model.form)}
                  </span>
                  <span style={{ marginLeft: "auto" }}>
                    <SgTrajectoryMeter
                      momentumTrend={p.model.momentum_trend}
                      momentumDirection={p.model.momentum_direction}
                      normMin={trajectoryBounds.min}
                      normMax={trajectoryBounds.max}
                    />
                  </span>
                </div>
              )}
            </div>
            {selectedKey === p.key && <ChevronRight size={10} style={{ color: "var(--green)", flexShrink: 0 }} />}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Full Player Profile View ─────────────────────────────────────────── */
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

  if (profileQuery.isLoading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10 }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", animation: "pulse-glow 1.8s ease-in-out infinite" }} />
        <div style={{ fontFamily: VAR.mono, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: VAR.faint }}>
          Loading {playerDisplay}…
        </div>
      </div>
    )
  }

  if (profileQuery.isError || !p) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontFamily: VAR.mono, fontSize: 10, color: VAR.faint, textAlign: "center" }}>
          <div style={{ marginBottom: 6, color: "var(--red)" }}>Failed to load profile</div>
          <div>Check that the backend is running and the player key is valid.</div>
        </div>
      </div>
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
            {p.has_skill_data && <span className="status-pill good">DG Skills ✓</span>}
            {p.has_ranking_data && <span className="status-pill good">Rankings ✓</span>}
            {p.has_approach_data && <span className="status-pill good">Approach ✓</span>}
            {!p.has_skill_data && !p.has_ranking_data && (
              <span className="status-pill warn">No live DG data</span>
            )}
          </div>
        </div>

        <div className="players-kpi-grid">
          {[
            { label: "DG Rank",    value: p.header.dg_rank  ? `#${p.header.dg_rank}`  : "—" },
            { label: "OWGR",       value: p.header.owgr_rank ? `#${p.header.owgr_rank}` : "—" },
            {
              label: "DG Skill",
              value: p.header.dg_skill_estimate != null ? signed(p.header.dg_skill_estimate, 2) : "—",
              tone: tone(p.header.dg_skill_estimate),
              accentUnit: p.header.dg_skill_estimate != null ? heatUnitForSg(p.header.dg_skill_estimate) : undefined,
            },
            {
              label: "Total SG",
              value: p.sg_skills.sg_total != null ? signed(p.sg_skills.sg_total) : "—",
              tone: tone(p.sg_skills.sg_total),
              accentUnit: p.sg_skills.sg_total != null ? heatUnitForSg(p.sg_skills.sg_total) : undefined,
            },
            { label: "Events (DB)",value: String(p.header.events_tracked ?? 0), sub: "tracked events" },
            { label: "Rounds (DB)",value: String(p.header.rounds_in_db ?? 0), sub: "stored rounds" },
          ].map((item, i, arr) => (
            <div key={item.label} className={cn("players-kpi-cell-wrap", i === arr.length - 1 && "players-kpi-cell-wrap--last")}>
              <KpiCell {...item} title={PLAYER_PAGE_KPI_TOOLTIPS[item.label]} />
            </div>
          ))}
        </div>
      </div>

      <div className="players-content">
        {modelPlayer && (
          <CollapsibleSection
            title="Model alignment"
            description="Current field model context"
            defaultOpen
          >
            <div className="profile-panel-body profile-panel-body--grid-5">
              <MetricCard label="Model Rank" value={`#${modelPlayer.rank}`} title={PLAYER_PROFILE_STAT_TOOLTIPS["Model Rank"]} />
              <MetricCard label="Composite" value={modelPlayer.composite.toFixed(1)} title={PLAYER_PROFILE_STAT_TOOLTIPS.Composite} />
              <MetricCard label="Form" value={modelPlayer.form.toFixed(1)} title={PLAYER_PROFILE_STAT_TOOLTIPS.Form} />
              <MetricCard label="Course Fit" value={modelPlayer.course_fit.toFixed(1)} title={PLAYER_PROFILE_STAT_TOOLTIPS["Course Fit"]} />
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
        )}

        {p.ranking_card && (
          <CollapsibleSection title="DG identity" description="Structured DataGolf ranking context">
            <div className="profile-panel-body profile-panel-body--grid-4">
              <MetricCard label="DG Rank" value={p.ranking_card.dg_rank ? `#${p.ranking_card.dg_rank}` : "—"} title={PLAYER_PROFILE_STAT_TOOLTIPS["DG Rank"]} />
              <MetricCard label="OWGR" value={p.ranking_card.owgr_rank ? `#${p.ranking_card.owgr_rank}` : "—"} title={PLAYER_PROFILE_STAT_TOOLTIPS.OWGR} />
              <MetricCard label="DG Skill" value={signed(p.ranking_card.dg_skill_estimate, 2)} tone={tone(p.ranking_card.dg_skill_estimate)} title={PLAYER_PROFILE_STAT_TOOLTIPS["DG Skill"]} />
              <MetricCard label="Primary Tour" value={p.ranking_card.primary_tour ?? "—"} title={PLAYER_PROFILE_STAT_TOOLTIPS["Primary Tour"]} />
            </div>
          </CollapsibleSection>
        )}

        {/* Skill profile row: radar + KPIs beside field distribution when width allows */}
        <CollapsibleSection title="Skill profile" description="Radar, driving stats, rolling windows" defaultOpen>
            <div className="profile-skill-radar-inner">
              <div className="profile-panel-body profile-panel-body--chart">
                <PentagonRadar skills={p.sg_skills} playerName={p.player_display} height={300} />
              </div>
              <div className="profile-skill-side">
                <div className="profile-section-label">Driving</div>
                <div className="profile-skill-metrics-2">
                  <MetricCard label="Distance" value={p.sg_skills.driving_dist ? `${p.sg_skills.driving_dist.toFixed(0)} yd` : "—"} title={PLAYER_PROFILE_STAT_TOOLTIPS.Distance} />
                  <MetricCard label="Accuracy" value={p.sg_skills.driving_acc ? `${(p.sg_skills.driving_acc * 100).toFixed(1)}%` : "—"} title={PLAYER_PROFILE_STAT_TOOLTIPS.Accuracy} />
                </div>
                <div className="profile-section-label" style={{ marginTop: 4 }}>Rolling windows</div>
                {(["10", "25", "50"] as const).map((w) => {
                  const val = p.rolling_windows?.[w]
                  const heatT = heatUnitForSg(val)
                  return (
                    <div key={w} title={ROLLING_WINDOW_ROW_TOOLTIP} className="profile-rolling-row">
                      <span className="profile-rolling-label">L{w}</span>
                      <span
                        className="profile-rolling-value"
                        style={{ color: val != null ? heatSpectrumFromUnit(heatT) : undefined }}
                      >
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

        {p.rolling_windows_expanded && (
          <CollapsibleSection title="Rolling windows grid" description="L10 / L25 / L50 by SG category">
            <div className="profile-panel-body profile-panel-body--scroll">
              <table className="profile-data-table">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${VAR.border}` }}>
                    {["Window", "TOTAL", "OTT", "APP", "ARG", "PUTT", "T2G"].map((head) => (
                      <th
                        key={head}
                        title={ROLLING_SG_GRID_HEADER_TOOLTIPS[head]}
                        style={{ textAlign: head === "Window" ? "left" : "center", color: VAR.muted, padding: "8px 10px", letterSpacing: "0.07em", fontWeight: 700 }}
                      >
                        {head}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(["10", "25", "50"] as const).map((windowKey) => {
                    const cells = [
                      p.rolling_windows_expanded?.sg_total?.[windowKey],
                      p.rolling_windows_expanded?.sg_ott?.[windowKey],
                      p.rolling_windows_expanded?.sg_app?.[windowKey],
                      p.rolling_windows_expanded?.sg_arg?.[windowKey],
                      p.rolling_windows_expanded?.sg_putt?.[windowKey],
                      p.rolling_windows_expanded?.sg_t2g?.[windowKey],
                    ]
                    return (
                      <tr key={windowKey} style={{ borderBottom: `1px solid ${VAR.divider}` }}>
                        <td title={ROLLING_WINDOW_ROW_TOOLTIP} style={{ padding: "8px", color: VAR.text, fontWeight: 700 }}>L{windowKey}</td>
                        {cells.map((value, index) => {
                          const heatT = heatUnitForSg(value)
                          return (
                            <td key={`${windowKey}-${index}`} style={{ padding: "10px 8px", textAlign: "center" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  minWidth: 58,
                                  padding: "5px 8px",
                                  borderRadius: 4,
                                  border: `1px solid ${VAR.border}`,
                                  background: heatSpectrumGradientAlongUnit(heatT, "ltr"),
                                  color: "var(--bg)",
                                  fontWeight: 700,
                                  fontSize: 12,
                                }}
                              >
                                {signed(value, 2)}
                              </span>
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CollapsibleSection>
        )}

        {p.recent_events.length > 0 && (
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
        )}

        {p.course_summaries && p.course_summaries.length > 0 && (
          <CollapsibleSection title="Course rollups" description="Most tracked courses by rounds played">
            <div className="profile-panel-body">
              <table className="profile-data-table">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${VAR.border}` }}>
                    <th style={{ textAlign: "left", color: VAR.faint, padding: "6px 8px", letterSpacing: "0.08em" }}>Course</th>
                    <th style={{ textAlign: "center", color: VAR.faint, padding: "6px 8px", letterSpacing: "0.08em" }}>Rounds</th>
                    <th style={{ textAlign: "center", color: VAR.faint, padding: "6px 8px", letterSpacing: "0.08em" }}>Avg SG Total</th>
                  </tr>
                </thead>
                <tbody>
                  {p.course_summaries.map((course) => (
                    <tr key={course.course_name} style={{ borderBottom: `1px solid ${VAR.divider}` }}>
                      <td style={{ padding: "8px", color: VAR.text }}>{course.course_name}</td>
                      <td style={{ padding: "8px", color: VAR.muted, textAlign: "center" }}>{course.rounds_played}</td>
                      <td style={{ padding: "8px", textAlign: "center", color: heatSpectrumFromUnit(heatUnitForSg(course.avg_sg_total)) }}>
                        {signed(course.avg_sg_total, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CollapsibleSection>
        )}

        {p.recent_rounds_sample && p.recent_rounds_sample.length > 0 && (
          <CollapsibleSection title="Round log" description="Recent rounds with SG splits">
            <div className="profile-panel-body profile-panel-body--scroll">
              <table className="profile-data-table">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${VAR.border}` }}>
                    {["Date", "Event", "R", "Score", "TOT", "OTT", "APP", "ARG", "PUTT", "T2G"].map((head) => (
                      <th key={head} style={{ textAlign: head === "Event" ? "left" : "center", color: VAR.faint, padding: "6px 8px", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>
                        {head}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {p.recent_rounds_sample.slice(0, 24).map((round: StandaloneRecentRoundSample, idx: number) => {
                    const values = [round.sg_total, round.sg_ott, round.sg_app, round.sg_arg, round.sg_putt, round.sg_t2g]
                    return (
                      <tr key={`${round.event_completed ?? "na"}-${round.round_num ?? idx}-${idx}`} style={{ borderBottom: `1px solid ${VAR.divider}` }}>
                        <td style={{ padding: "6px 8px", color: VAR.faint, textAlign: "center", whiteSpace: "nowrap" }}>{round.event_completed ?? "—"}</td>
                        <td style={{ padding: "6px 8px", color: VAR.text, whiteSpace: "nowrap" }}>{round.event_name ?? "—"}</td>
                        <td style={{ padding: "6px 8px", color: VAR.muted, textAlign: "center" }}>{round.round_num ?? "—"}</td>
                        <td style={{ padding: "6px 8px", color: VAR.text, textAlign: "center" }}>{round.score ?? "—"}</td>
                        {values.map((value, valueIdx) => (
                          <td
                            key={`${idx}-${valueIdx}`}
                            style={{
                              padding: "6px 8px",
                              textAlign: "center",
                              color: value != null ? heatSpectrumFromUnit(heatUnitForSg(value)) : VAR.faint,
                            }}
                          >
                            {signed(value, 2)}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CollapsibleSection>
        )}

        {/* ── Row 4: Approach Arc Gauges ──────────────────────────── */}
        {p.approach_buckets.length > 0 && (() => {
          // Parse the approach_buckets (FW/Rough pairs) into ApproachBucket[]  
          const bucketMap: Record<string, { fw?: number; rgh?: number }> = {}
          for (const b of p.approach_buckets) {
            const isFw  = b.label.toLowerCase().includes("fw") || b.key.toLowerCase().includes("_fw")
            const range = b.label.replace(/ ?FW| ?Rgh| ?Rough/gi, "").trim()
            if (!bucketMap[range]) bucketMap[range] = {}
            if (isFw) bucketMap[range].fw  = b.value
            else       bucketMap[range].rgh = b.value
          }
          const arcBuckets: ApproachBucket[] = Object.entries(bucketMap)
            .filter(([, v]) => v.fw != null || v.rgh != null)
            .map(([label, v]) => ({ label, fw_sg: v.fw ?? 0, rgh_sg: v.rgh ?? 0 }))

          if (!arcBuckets.length) return null
          return (
            <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
              <div className="panel-header">
                <span className="panel-label">Approach by Distance</span>
                <span className="panel-label-dim">Semicircle arc per yardage bucket — tick marks = tour average</span>
              </div>
              <div style={{ padding: 12 }}>
                <ApproachArcGauges buckets={arcBuckets} />
              </div>
            </div>
          )
        })()}

        {/* ── Row 5: Tournament History Table ────────────────────── */}
        {p.recent_events.length > 0 && (
          <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
            <div className="panel-header">
              <span className="panel-label">Tournament History</span>
              <span className="panel-label-dim">Win = gold · Top 10 = green · MC = red — inline SG bars per category</span>
            </div>
            <div style={{ padding: 12 }}>
              <HistoryTable
                events={p.recent_events as HistoryEvent[]}
                maxRows={16}
              />
            </div>
          </div>
        )}

        {!p.has_skill_data && !p.has_ranking_data && !p.has_approach_data && p.recent_events.length === 0 && (
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
            <div style={{ fontFamily: VAR.mono, fontSize: 10, color: VAR.faint, textTransform: "uppercase", letterSpacing: "0.1em" }}>
              No data available for this player
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint }}>
              Ensure DATAGOLF_API_KEY is set and round data has been backfilled.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Empty State ──────────────────────────────────────────────────────── */
function EmptyState() {
  return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10 }}>
      <User size={24} style={{ color: "var(--text-faint)" }} />
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-faint)", textAlign: "center", lineHeight: 1.8 }}>
        Select a player from the list<br/>to view their full profile
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   ROOT EXPORT — PlayersPage
══════════════════════════════════════════════════════════════════════ */
export function PlayersPage({
  players,
}: {
  players: CompositePlayer[]
  // legacy props ignored — the page manages its own selection state
  selectedPlayerProfile?: unknown
  onPlayerSelect?: (key: string) => void
  richProfilesEnabled?: boolean
}) {
  const initialFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("player")
      : null
  const [selectedKey, setSelectedKey] = useState<string | null>(initialFromUrl)
  const [selectedDisplay, setSelectedDisplay] = useState<string>("")
  const trajectoryBounds = useMemo(() => computeSgTrajectoryBounds(players), [players])

  const handleSelect = useCallback((key: string, display: string) => {
    setSelectedKey(key)
    setSelectedDisplay(display)
  }, [])

  // Auto-select first active player once the field has loaded.
  // Resolve during render to avoid a setState-in-effect cascade.
  const first = players[0]
  const effectiveKey = selectedKey ?? first?.player_key ?? null
  const fallbackSelectedDisplay = selectedKey
    ? players.find((player) => player.player_key === selectedKey)?.player_display ?? selectedKey.replaceAll("_", " ")
    : ""
  const effectiveDisplay = selectedKey ? (selectedDisplay || fallbackSelectedDisplay) : (first?.player_display ?? "")

  useEffect(() => {
    if (!effectiveKey || typeof window === "undefined") return
    const url = new URL(window.location.href)
    url.searchParams.set("player", effectiveKey)
    window.history.replaceState({}, "", url.toString())
  }, [effectiveKey])

  return (
    <div className="players-layout">
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
          <EmptyState />
        )}
      </div>
    </div>
  )
}
