/**
 * Standalone Players Page
 * Full DataGolf-style player profiles accessible without an active tournament.
 * Route: /players
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, User, ChevronRight, X } from "lucide-react"

import {
  SgSkillBarsChart,
  SgRollingChart,
  ApproachBucketsChart,
  TournamentHistoryChart,
  SparklineChart,
} from "@/components/charts"
import { api } from "@/lib/api"
import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"

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

/* ── Window selector ─────────────────────────────────────────────────── */
type RollingWindow = "10" | "25" | "50"
const WINDOWS: RollingWindow[] = ["10", "25", "50"]

/* ── KPI Cell ─────────────────────────────────────────────────────────── */
function KpiCell({
  label,
  value,
  tone: t = "neutral",
  sub,
  large = false,
}: {
  label: string
  value: string | React.ReactNode
  tone?: Tone
  sub?: string
  large?: boolean
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 2,
        padding: "10px 14px",
        minWidth: 0,
      }}
    >
      <span style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: VAR.faint }}>
        {label}
      </span>
      <span style={{ fontFamily: VAR.mono, fontSize: large ? 22 : 17, fontWeight: 700, color: toneColor(t), letterSpacing: "-0.02em", lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </span>
      {sub && <span style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint }}>{sub}</span>}
    </div>
  )
}

/* ── Stat metric card ─────────────────────────────────────────────────── */
function MetricCard({ label, value, tone: t = "neutral", sub }: { label: string; value: string | React.ReactNode; tone?: Tone; sub?: string }) {
  return (
    <div style={{ background: VAR.surface, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", padding: "8px 10px" }}>
      <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontFamily: VAR.mono, fontSize: 18, fontWeight: 700, color: toneColor(t), letterSpacing: "-0.02em", lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {sub && <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

/* ── Section header ───────────────────────────────────────────────────── */
function SectionHead({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
      <div style={{ fontFamily: VAR.mono, fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: VAR.muted }}>
        {children}
      </div>
      {actions}
    </div>
  )
}

/* ── ChartLabel ───────────────────────────────────────────────────────── */
function ChartLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 6, marginTop: 12 }}>
      {children}
    </div>
  )
}

/* ── Player Search Sidebar ────────────────────────────────────────────── */
function PlayerSearchSidebar({
  activePlayers,
  selectedKey,
  onSelect,
}: {
  activePlayers: CompositePlayer[]
  selectedKey: string | null
  onSelect: (key: string, display: string) => void
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
  const searchResults = searchQuery.data?.players ?? []

  // Active field players filtered by query
  const filteredActive = useMemo(() => {
    if (!query) return activePlayers.slice(0, 30)
    const q = query.toLowerCase()
    return activePlayers.filter((p) =>
      p.player_display.toLowerCase().includes(q) || p.player_key.includes(q)
    ).slice(0, 20)
  }, [activePlayers, query])

  // Merge: active field + DB results (deduplicated)
  const displayList = useMemo(() => {
    if (!showSearch) return filteredActive.map((p) => ({ key: p.player_key, display: p.player_display, inField: true }))
    const activeKeys = new Set(filteredActive.map((p) => p.player_key))
    const dbOnly = searchResults.filter((r) => !activeKeys.has(r.player_key))
    return [
      ...filteredActive.map((p) => ({ key: p.player_key, display: p.player_display, inField: true })),
      ...dbOnly.map((r) => ({ key: r.player_key, display: r.player_display, inField: false })),
    ]
  }, [filteredActive, searchResults, showSearch])

  return (
    <div
      style={{
        width: 220,
        flexShrink: 0,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: VAR.bg1,
        borderRight: `1px solid ${VAR.border}`,
        overflow: "hidden",
      }}
    >
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
              background: selectedKey === p.key ? "var(--green-bg)" : "none",
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
                  color: selectedKey === p.key ? "var(--green)" : VAR.text,
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
            </div>
            {selectedKey === p.key && <ChevronRight size={10} style={{ color: "var(--green)", flexShrink: 0 }} />}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Full Player Profile View ─────────────────────────────────────────── */
function PlayerProfileView({ playerKey, playerDisplay }: { playerKey: string; playerDisplay: string }) {
  const [rollingWindow, setRollingWindow] = useState<RollingWindow>("25")

  const profileQuery = useQuery({
    queryKey: ["standalone-profile", playerKey],
    queryFn: () => api.getPlayerStandaloneProfile(playerKey),
    staleTime: 5 * 60_000,
    gcTime: 15 * 60_000,
  })

  const p = profileQuery.data

  if (profileQuery.isLoading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 10 }}>
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--cyan)", animation: "pulse-glow 1.8s ease-in-out infinite" }} />
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

  /* Build SG skills array for chart */
  const sgSkills = [
    { label: "Off the Tee",    value: p.sg_skills.sg_ott ?? null },
    { label: "Approach",       value: p.sg_skills.sg_app ?? null },
    { label: "Around Green",   value: p.sg_skills.sg_arg ?? null },
    { label: "Putting",        value: p.sg_skills.sg_putt ?? null },
    { label: "Total SG",       value: p.sg_skills.sg_total ?? null },
  ].filter((s) => s.value != null) as Array<{ label: string; value: number }>

  const windowValue = p.rolling_windows[rollingWindow]

  return (
    <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 0, minHeight: 0 }}>
      {/* ── Player Header Strip ───────────────────────────────────── */}
      <div
        style={{
          background: VAR.bg2,
          borderBottom: `1px solid ${VAR.border}`,
          padding: "10px 16px 8px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
          <div>
            <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: VAR.faint, marginBottom: 3 }}>
              Player Profile
            </div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 20, fontWeight: 800, color: VAR.text, letterSpacing: "-0.01em", lineHeight: 1 }}>
              {p.player_display}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0, marginTop: 2 }}>
            {p.has_skill_data && <span className="status-pill good">DG Skills ✓</span>}
            {p.has_ranking_data && <span className="status-pill good">Rankings ✓</span>}
            {p.has_approach_data && <span className="status-pill good">Approach ✓</span>}
            {!p.has_skill_data && !p.has_ranking_data && (
              <span className="status-pill warn">No live DG data</span>
            )}
          </div>
        </div>

        {/* KPI Strip */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(6, 1fr)",
            background: VAR.bg1,
            border: `1px solid ${VAR.border}`,
            borderRadius: "var(--r-md)",
            overflow: "hidden",
          }}
        >
          {[
            { label: "DG Rank",    value: p.header.dg_rank  ? `#${p.header.dg_rank}`  : "—" },
            { label: "OWGR",       value: p.header.owgr_rank ? `#${p.header.owgr_rank}` : "—" },
            { label: "DG Skill",   value: p.header.dg_skill_estimate != null ? signed(p.header.dg_skill_estimate, 2) : "—", tone: tone(p.header.dg_skill_estimate) },
            { label: "Total SG",   value: p.sg_skills.sg_total != null ? signed(p.sg_skills.sg_total) : "—", tone: tone(p.sg_skills.sg_total) },
            { label: "Events (DB)",value: String(p.header.events_tracked ?? 0), sub: "tracked events" },
            { label: "Rounds (DB)",value: String(p.header.rounds_in_db ?? 0), sub: "stored rounds" },
          ].map((item, i, arr) => (
            <div
              key={item.label}
              style={{
                borderRight: i < arr.length - 1 ? `1px solid ${VAR.border}` : "none",
              }}
            >
              <KpiCell {...item} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────────── */}
      <div style={{ flex: 1, padding: "12px 16px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* ── Row 1: SG Skills + Driving ─────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 12 }}>

          {/* SG Skill Bars */}
          <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
            <div className="panel-header">
              <span className="panel-label">SG Skill Profile</span>
              <span className="panel-label-dim">Strokes gained per round vs tour average (0.000)</span>
            </div>
            <div style={{ padding: 12 }}>
              {sgSkills.length > 0 ? (
                <SgSkillBarsChart skills={sgSkills} height={Math.max(130, sgSkills.length * 30 + 20)} />
              ) : (
                <div style={{ padding: "20px 0", fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, textAlign: "center", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  SG skill data not available — requires active DataGolf API key
                </div>
              )}
            </div>
          </div>

          {/* Driving + meta stats */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ fontFamily: VAR.mono, fontSize: 8.5, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.muted, marginBottom: 2 }}>
              Driving
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              <MetricCard label="Distance" value={p.sg_skills.driving_dist ? `${p.sg_skills.driving_dist.toFixed(0)} yd` : "—"} />
              <MetricCard label="Accuracy" value={p.sg_skills.driving_acc ? `${(p.sg_skills.driving_acc * 100).toFixed(1)}%` : "—"} />
            </div>

            <div style={{ fontFamily: VAR.mono, fontSize: 8.5, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.muted, marginTop: 4, marginBottom: 2 }}>
              Rolling Form
            </div>
            <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  type="button"
                  onClick={() => setRollingWindow(w)}
                  style={{
                    flex: 1,
                    padding: "4px 0",
                    borderRadius: "var(--r-sm)",
                    fontFamily: VAR.mono,
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    cursor: "pointer",
                    border: "1px solid",
                    transition: "all 120ms",
                    ...(w === rollingWindow
                      ? { background: "rgba(34,211,238,0.12)", color: "var(--cyan)", borderColor: "rgba(34,211,238,0.25)" }
                      : { background: "transparent", color: VAR.muted, borderColor: VAR.border }),
                  }}
                >
                  L{w}
                </button>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              <MetricCard
                label={`Avg SG (L${rollingWindow})`}
                value={signed(windowValue)}
                tone={tone(windowValue)}
                sub="strokes / round"
              />
              <MetricCard
                label="Trend"
                value={p.trend_series.length > 1
                  ? signed((p.trend_series[p.trend_series.length - 1] ?? 0) - (p.trend_series[0] ?? 0))
                  : "—"}
                tone={p.trend_series.length > 1
                  ? tone((p.trend_series[p.trend_series.length - 1] ?? 0) - (p.trend_series[0] ?? 0))
                  : "neutral"}
                sub="recent vs oldest"
              />
            </div>

            {/* Mini sparkline */}
            {p.trend_series.length > 3 && (
              <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", padding: "8px 10px", marginTop: 4 }}>
                <div style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.faint, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
                  SG Trend (last {Math.min(p.trend_series.length, 50)} rounds)
                </div>
                <SparklineChart values={p.trend_series.slice(-50)} color="var(--cyan)" height={60} />
              </div>
            )}
          </div>
        </div>

        {/* ── Row 2: Full Rolling Form Chart ─────────────────────── */}
        {p.trend_series.length > 0 && (
          <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
            <div className="panel-header">
              <span className="panel-label">Rolling SG Form</span>
              <span className="panel-label-dim">SG/round per round (oldest → newest) — dashed = tour avg (0.000)</span>
            </div>
            <div style={{ padding: 12 }}>
              <SgRollingChart values={p.trend_series} height={170} />
            </div>
          </div>
        )}

        {/* ── Row 3: Approach Buckets ─────────────────────────────── */}
        {p.approach_buckets.length > 0 && (
          <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
            <div className="panel-header">
              <span className="panel-label">Approach — Distance Buckets</span>
              <span className="panel-label-dim">SG per shot by yardage band and lie (fairway vs rough)</span>
            </div>
            <div style={{ padding: 12 }}>
              <ApproachBucketsChart buckets={p.approach_buckets} height={180} />
            </div>
          </div>
        )}

        {/* ── Row 4: Tournament History ────────────────────────────── */}
        {p.recent_events.length > 0 && (
          <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", overflow: "hidden" }}>
            <div className="panel-header">
              <span className="panel-label">Recent Events</span>
              <span className="panel-label-dim">Avg SG/round per event · green = elite, red = poor/missed cut</span>
            </div>
            <div style={{ padding: 12 }}>
              <TournamentHistoryChart events={p.recent_events} height={160} />
            </div>

            {/* Summary table */}
            <div style={{ borderTop: `1px solid ${VAR.border}`, overflow: "hidden" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Date</th>
                    <th className="center">Finish</th>
                    <th className="right">Avg SG</th>
                    <th className="right">Rounds</th>
                  </tr>
                </thead>
                <tbody>
                  {p.recent_events.slice(0, 12).map((evt, i) => {
                    const sg = evt.avg_sg_total
                    const t = tone(sg)
                    return (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, color: VAR.text }}>{evt.event_name}</td>
                        <td style={{ color: VAR.faint, fontSize: 11 }}>{evt.event_completed ?? "—"}</td>
                        <td className="center">
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: VAR.muted }}>
                            {evt.fin_text ?? "—"}
                          </span>
                        </td>
                        <td className="right num" style={{ fontWeight: 700, color: toneColor(t) }}>
                          {signed(sg)}
                        </td>
                        <td className="right num" style={{ color: VAR.faint, fontSize: 11 }}>
                          {evt.rounds_played ?? "—"}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
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
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [selectedDisplay, setSelectedDisplay] = useState<string>("")

  const handleSelect = useCallback((key: string, display: string) => {
    setSelectedKey(key)
    setSelectedDisplay(display)
  }, [])

  // Auto-select first active player if none selected and field is loaded
  useEffect(() => {
    if (!selectedKey && players.length > 0) {
      const first = players[0]
      setSelectedKey(first.player_key)
      setSelectedDisplay(first.player_display)
    }
  }, [players, selectedKey])

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Sidebar */}
      <PlayerSearchSidebar
        activePlayers={players}
        selectedKey={selectedKey}
        onSelect={handleSelect}
      />

      {/* Main profile view */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {selectedKey ? (
          <PlayerProfileView key={selectedKey} playerKey={selectedKey} playerDisplay={selectedDisplay} />
        ) : (
          <EmptyState />
        )}
      </div>
    </div>
  )
}
