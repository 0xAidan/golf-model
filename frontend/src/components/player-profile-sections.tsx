import { useMemo, useState } from "react"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"

import {
  SgSkillBarsChart,
  SgRollingChart,
  ApproachBucketsChart,
  TournamentHistoryChart,
  SparklineChart,
} from "@/components/charts"
import { formatNumber } from "@/lib/format"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

/* ── Tokens ─────────────────────────────────────────────────────────── */
const VAR = {
  bg1:        "var(--bg-1)",
  bg2:        "var(--bg-2)",
  surface:    "var(--surface)",
  surface2:   "var(--surface-2)",
  border:     "var(--border)",
  divider:    "var(--divider)",
  text:       "var(--text)",
  muted:      "var(--text-muted)",
  faint:      "var(--text-faint)",
  green:      "var(--green)",
  cyan:       "var(--cyan)",
  gold:       "var(--gold)",
  red:        "var(--red)",
  amber:      "var(--amber)",
  mono:       "var(--font-mono)",
}

/* ── Helpers ─────────────────────────────────────────────────────────── */
type Tone = "positive" | "negative" | "neutral"

function toneFn(v?: number | null): Tone {
  if (v == null) return "neutral"
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"
}

function toneColor(tone: Tone) {
  return tone === "positive" ? VAR.green : tone === "negative" ? VAR.red : VAR.muted
}

function signed(v?: number | null, digits = 3): string {
  if (v == null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(digits)}`
}

/* ── Sub-components ──────────────────────────────────────────────────── */
function SectionPanel({
  label,
  children,
  defaultOpen = true,
}: {
  label: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div
      style={{
        background: VAR.bg1,
        border: `1px solid ${VAR.border}`,
        borderRadius: "var(--r-md)",
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 10px",
          height: 30,
          background: VAR.bg2,
          border: "none",
          borderBottom: open ? `1px solid ${VAR.border}` : "none",
          cursor: "pointer",
        }}
      >
        <span
          style={{
            fontFamily: VAR.mono,
            fontSize: 9.5,
            fontWeight: 700,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: VAR.muted,
          }}
        >
          {label}
        </span>
        <span style={{ color: VAR.faint, fontSize: 10, fontFamily: VAR.mono }}>
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && <div style={{ padding: 10 }}>{children}</div>}
    </div>
  )
}

function KpiRow({ items }: { items: Array<{ label: string; value: string | React.ReactNode; tone?: Tone; sub?: string }> }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${items.length}, 1fr)`,
        borderBottom: `1px solid ${VAR.border}`,
        marginBottom: 10,
      }}
    >
      {items.map((item, i) => (
        <div
          key={item.label}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 2,
            padding: "8px 12px",
            borderRight: i < items.length - 1 ? `1px solid ${VAR.border}` : "none",
          }}
        >
          <span
            style={{
              fontFamily: VAR.mono,
              fontSize: 8.5,
              fontWeight: 600,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: VAR.faint,
            }}
          >
            {item.label}
          </span>
          <span
            style={{
              fontFamily: VAR.mono,
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: item.tone ? toneColor(item.tone) : VAR.text,
              fontVariantNumeric: "tabular-nums",
              lineHeight: 1,
            }}
          >
            {item.value}
          </span>
          {item.sub && (
            <span style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint }}>{item.sub}</span>
          )}
        </div>
      ))}
    </div>
  )
}

function StatRow({ label, value, tone, mono = true }: { label: string; value: string | React.ReactNode; tone?: Tone; mono?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "5px 0",
        borderBottom: `1px solid ${VAR.divider}`,
      }}
    >
      <span style={{ fontFamily: VAR.mono, fontSize: 10, color: VAR.muted, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </span>
      <span
        style={{
          fontFamily: mono ? VAR.mono : "inherit",
          fontSize: 12,
          fontWeight: 700,
          fontVariantNumeric: "tabular-nums",
          color: tone ? toneColor(tone) : VAR.text,
        }}
      >
        {value}
      </span>
    </div>
  )
}

function ChartLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: VAR.mono,
        fontSize: 8.5,
        fontWeight: 600,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: VAR.faint,
        marginBottom: 6,
        marginTop: 2,
      }}
    >
      {children}
    </div>
  )
}

/* ── Window/Benchmark Pill Buttons ───────────────────────────────────── */
function PillGroup<T extends string>({
  options,
  labels,
  active,
  color,
  onSelect,
}: {
  options: T[]
  labels?: Record<T, string>
  active: T
  color: "cyan" | "green" | "gold"
  onSelect: (v: T) => void
}) {
  const activeStyle = {
    cyan:  { background: "rgba(34,197,94,0.15)",  color: "var(--green)", border: "1px solid rgba(34,197,94,0.35)" },
    green: { background: "rgba(34,197,94,0.12)",  color: "var(--green)", border: "1px solid rgba(34,197,94,0.25)" },
    gold:  { background: "rgba(245,180,24,0.10)", color: "var(--gold)",  border: "1px solid rgba(245,180,24,0.25)" },
  }[color]

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onSelect(opt)}
          style={{
            padding: "3px 9px",
            borderRadius: 2,
            fontFamily: VAR.mono,
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            cursor: "pointer",
            transition: "all 120ms",
            ...(opt === active
              ? activeStyle
              : { background: "transparent", color: VAR.muted, border: `1px solid ${VAR.border}` }),
          }}
        >
          {labels ? labels[opt] : opt}
        </button>
      ))}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   SECTION 1 — Ranking Header
══════════════════════════════════════════════════════════════════════ */
function RankingHeaderSection({
  player,
  profile,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
}) {
  const dgRank  = profile?.header?.dg_rank
  const owgr    = profile?.header?.owgr_rank
  const skill   = profile?.header?.dg_skill_estimate
  const form    = player.form
  const course  = player.course_fit
  const momentum = player.momentum

  return (
    <SectionPanel label="Player Overview">
      <KpiRow
        items={[
          { label: "Model Rank",  value: `#${player.rank}` },
          { label: "Composite",   value: formatNumber(player.composite, 1), tone: "positive" },
          { label: "DG Rank",     value: dgRank ? `#${dgRank}` : "—" },
          { label: "OWGR",        value: owgr   ? `#${owgr}`   : "—" },
          { label: "DG Skill",    value: skill  ? formatNumber(skill, 2) : "—", tone: toneFn(skill) },
        ]}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        {[
          { label: "Course Fit", value: formatNumber(course, 1),    tone: toneFn(course),    sub: `${profile?.header?.course_rounds_tracked ?? player.course_rounds ?? 0} rounds tracked` },
          { label: "Form",       value: formatNumber(form, 1),      tone: toneFn(form),      sub: "recent SG signal" },
          { label: "Momentum",   value: formatNumber(momentum, 1),  tone: toneFn(momentum),  sub: player.momentum_direction ?? "" },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: VAR.surface,
              border: `1px solid ${VAR.border}`,
              borderRadius: "var(--r-md)",
              padding: "8px 10px",
            }}
          >
            <div style={{ fontFamily: VAR.mono, fontSize: 8.5, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 3 }}>
              {item.label}
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 18, fontWeight: 700, color: toneColor(item.tone), letterSpacing: "-0.02em", lineHeight: 1 }}>
              {item.value}
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, marginTop: 2 }}>{item.sub}</div>
          </div>
        ))}
      </div>
    </SectionPanel>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   SECTION 2 — SG Skill Breakdown (diverging bars)
══════════════════════════════════════════════════════════════════════ */
function SkillBreakdownSection({ player, profile }: { player: CompositePlayer; profile?: PlayerProfile }) {
  const primary = profile?.skill_breakdown?.primary ?? []
  const bestArea    = profile?.skill_breakdown?.summary?.best_area
  const weakestArea = profile?.skill_breakdown?.summary?.weakest_area

  const skills = primary.map((s) => ({
    label: s.label,
    value: s.value,
  }))

  return (
    <SectionPanel label="SG Skill Profile">
      {skills.length > 0 ? (
        <>
          {(bestArea || weakestArea) && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 10 }}>
              {bestArea && (
                <div style={{ background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.18)", borderRadius: "var(--r-md)", padding: "7px 10px" }}>
                  <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--green)", marginBottom: 2 }}>
                    ▲ Strength
                  </div>
                  <div style={{ fontFamily: VAR.mono, fontSize: 12, fontWeight: 700, color: VAR.text }}>
                    {bestArea.label} <span style={{ color: "var(--green)" }}>{signed(bestArea.value)}</span>
                  </div>
                </div>
              )}
              {weakestArea && (
                <div style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.18)", borderRadius: "var(--r-md)", padding: "7px 10px" }}>
                  <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--red)", marginBottom: 2 }}>
                    ▼ Weakness
                  </div>
                  <div style={{ fontFamily: VAR.mono, fontSize: 12, fontWeight: 700, color: VAR.text }}>
                    {weakestArea.label} <span style={{ color: "var(--red)" }}>{signed(weakestArea.value)}</span>
                  </div>
                </div>
              )}
            </div>
          )}
          <ChartLabel>SG Per Round vs Tour Average (0.000)</ChartLabel>
          <SgSkillBarsChart skills={skills} height={Math.max(120, skills.length * 28 + 16)} />
        </>
      ) : (
        <>
          {/* Fallback to player composite components */}
          <ChartLabel>Model Score Components</ChartLabel>
          <SgSkillBarsChart
            skills={Object.entries(player.details?.course_components ?? {}).map(([k, v]) => ({
              label: k.replaceAll("_", " "),
              value: v,
            }))}
            height={120}
          />
          <p style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, marginTop: 6 }}>
            DG skill breakdown not yet available — showing model score components.
          </p>
        </>
      )}
    </SectionPanel>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   SECTION 3 — Rolling Form (line chart + window/benchmark selectors)
══════════════════════════════════════════════════════════════════════ */
type RollingWindow = "10" | "25" | "50"
type Benchmark = "tour_avg" | "top50" | "top10"

const WINDOW_OPTS: RollingWindow[] = ["10", "25", "50"]
const BENCH_OPTS: Benchmark[] = ["tour_avg", "top50", "top10"]
const BENCH_LABELS: Record<Benchmark, string> = { tour_avg: "Tour Avg", top50: "Top 50", top10: "Top 10" }

function RollingFormSection({ profile }: { profile?: PlayerProfile }) {
  const [window, setWindow] = useState<RollingWindow>("25")
  const [bench, setBench] = useState<Benchmark>("tour_avg")

  const rolling = profile?.rolling_form
  const trendValues = useMemo(() => {
    if (rolling?.trend_series?.length) return rolling.trend_series
    return (profile?.recent_rounds ?? [])
      .map((r) => Number(r.sg_total ?? 0))
      .reverse()
  }, [rolling, profile?.recent_rounds])

  const windowVal   = rolling?.windows?.[window] ?? null
  const benchVal    = rolling?.benchmarks?.[bench]?.[window] ?? null
  const edgeVsBench = windowVal != null && benchVal != null ? windowVal - benchVal : null
  const shortVsMed  = rolling?.summary?.delta_short_vs_medium

  const toneW = toneFn(windowVal)
  const toneE = toneFn(edgeVsBench)

  return (
    <SectionPanel label="Rolling Form">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 10 }}>
        <div>
          <div style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.faint, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
            Window
          </div>
          <PillGroup options={WINDOW_OPTS} active={window} color="green" onSelect={setWindow}
            labels={{ "10": "L10", "25": "L25", "50": "L50" } as Record<RollingWindow, string>}
          />
        </div>
        <div>
          <div style={{ fontFamily: VAR.mono, fontSize: 8, color: VAR.faint, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
            Benchmark
          </div>
          <PillGroup options={BENCH_OPTS} labels={BENCH_LABELS} active={bench} color="gold" onSelect={setBench} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 12 }}>
        {[
          { label: `Avg SG (L${window})`, value: signed(windowVal),    tone: toneW,    sub: "strokes gained / round" },
          { label: `${BENCH_LABELS[bench]} SG`, value: signed(benchVal), tone: "neutral" as Tone, sub: "benchmark" },
          { label: "Edge vs Bench",   value: signed(edgeVsBench),   tone: toneE,    sub: shortVsMed != null ? `Δ short/med: ${signed(shortVsMed, 3)}` : "" },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: VAR.surface,
              border: `1px solid ${VAR.border}`,
              borderRadius: "var(--r-md)",
              padding: "8px 10px",
            }}
          >
            <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 3 }}>
              {item.label}
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 20, fontWeight: 700, color: toneColor(item.tone as Tone), letterSpacing: "-0.02em", lineHeight: 1 }}>
              {item.value}
            </div>
            {item.sub && <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint, marginTop: 2 }}>{item.sub}</div>}
          </div>
        ))}
      </div>

      <ChartLabel>SG / Round Trend (oldest → newest, {trendValues.length} rounds)</ChartLabel>
      {trendValues.length > 0 ? (
        <SgRollingChart
          values={trendValues}
          benchmarkValue={benchVal}
          benchmarkLabel={BENCH_LABELS[bench]}
          height={160}
        />
      ) : (
        <SparklineChart values={[]} />
      )}
    </SectionPanel>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   SECTION 4 — Course / Event Context
══════════════════════════════════════════════════════════════════════ */
function CourseEventSection({ profile }: { profile?: PlayerProfile }) {
  const ctx         = profile?.course_event_context
  const recentStarts = ctx?.recent_starts ?? []
  const recentSummary = ctx?.recent_summary
  const courseSummary = ctx?.course_summary
  const courseValues = (profile?.course_history ?? [])
    .map((r) => Number(r.sg_total ?? 0))
    .filter((v) => !isNaN(v))
    .reverse()

  // Build events for chart
  const chartEvents = recentStarts.map((s) => ({
    event_name: s.event_name ?? "Unknown",
    avg_sg_total: s.avg_sg_total ?? null,
    fin_text: s.fin_text,
  }))

  return (
    <SectionPanel label="Recent Tournament History">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 6, marginBottom: 10 }}>
        {[
          { label: "Events Tracked",  value: String(recentSummary?.events_tracked ?? 0) },
          { label: "Cuts Made",       value: String(recentSummary?.made_cuts ?? 0) },
          { label: "Recent Avg SG",   value: signed(recentSummary?.avg_sg_total), tone: toneFn(recentSummary?.avg_sg_total) },
          { label: "Course Avg SG",   value: signed(courseSummary?.avg_sg_total), tone: toneFn(courseSummary?.avg_sg_total) },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              background: VAR.surface,
              border: `1px solid ${VAR.border}`,
              borderRadius: "var(--r-md)",
              padding: "7px 10px",
            }}
          >
            <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 2 }}>
              {item.label}
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 16, fontWeight: 700, color: item.tone ? toneColor(item.tone) : VAR.text, letterSpacing: "-0.02em" }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {chartEvents.length > 0 && (
        <>
          <ChartLabel>Avg SG by Event (most recent right)</ChartLabel>
          <TournamentHistoryChart events={chartEvents} height={150} />
        </>
      )}

      {courseValues.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <ChartLabel>Course History SG Trend</ChartLabel>
          <SparklineChart values={courseValues} color="var(--green)" height={70} />
        </div>
      )}

      {/* Recent starts table */}
      {recentStarts.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <table className="data-table" style={{ fontSize: 11 }}>
            <thead>
              <tr>
                <th>Event</th>
                <th>Date</th>
                <th className="center">Finish</th>
                <th className="right">Avg SG</th>
              </tr>
            </thead>
            <tbody>
              {recentStarts.slice(0, 8).map((event, i) => {
                const sg = event.avg_sg_total
                const tone = toneFn(sg)
                return (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: VAR.text }}>{event.event_name ?? "—"}</td>
                    <td style={{ color: VAR.faint, fontSize: 10 }}>{event.event_completed ?? "—"}</td>
                    <td className="center">
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: VAR.muted }}>
                        {event.fin_text ?? "—"}
                      </span>
                    </td>
                    <td
                      className="right num"
                      style={{ fontWeight: 700, color: toneColor(tone) }}
                    >
                      {signed(sg)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionPanel>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   SECTION 5 — Betting Context
══════════════════════════════════════════════════════════════════════ */
function BettingSection({ profile }: { profile?: PlayerProfile }) {
  const bets    = profile?.linked_bets ?? []
  const summary = profile?.betting_context?.summary

  return (
    <SectionPanel label="Betting Context" defaultOpen={false}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 10 }}>
        {[
          { label: "Linked Bets",       value: String(summary?.linked_bet_count ?? bets.length) },
          { label: "Avg EV",            value: signed(summary?.average_ev), tone: toneFn(summary?.average_ev) },
          { label: "High Confidence",   value: String(summary?.high_confidence_count ?? 0) },
        ].map((item) => (
          <div key={item.label} style={{ background: VAR.surface, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", padding: "7px 10px" }}>
            <div style={{ fontFamily: VAR.mono, fontSize: 8, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.faint, marginBottom: 2 }}>
              {item.label}
            </div>
            <div style={{ fontFamily: VAR.mono, fontSize: 18, fontWeight: 700, color: item.tone ? toneColor(item.tone) : VAR.text, letterSpacing: "-0.02em" }}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
      {bets.length > 0 ? (
        <table className="data-table" style={{ fontSize: 11 }}>
          <thead>
            <tr>
              <th>Bet</th>
              <th>Odds</th>
              <th className="right">EV</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {bets.slice(0, 6).map((bet, i) => {
              const tone = toneFn(bet.ev)
              return (
                <tr key={i}>
                  <td>
                    <div style={{ fontWeight: 600, color: VAR.text }}>{bet.bet_type ?? "—"}</div>
                    <div style={{ fontSize: 10, color: VAR.faint }}>
                      {bet.player_display}{bet.opponent_display ? ` vs ${bet.opponent_display}` : ""}
                    </div>
                  </td>
                  <td style={{ fontWeight: 600, fontFamily: "var(--font-mono)", color: VAR.green }}>{bet.market_odds ?? "—"}</td>
                  <td className="right num" style={{ fontWeight: 700, color: toneColor(tone) }}>{signed(bet.ev)}</td>
                  <td>
                    <span className={`tier-badge ${(bet.confidence ?? "LEAN").toUpperCase()}`}>
                      {bet.confidence ?? "—"}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      ) : (
        <div style={{ fontFamily: VAR.mono, fontSize: 10, color: VAR.faint, padding: "8px 0" }}>
          No linked bets in current run.
        </div>
      )}
    </SectionPanel>
  )
}

/* ══════════════════════════════════════════════════════════════════════
   ROOT EXPORT — PlayerProfileSections
══════════════════════════════════════════════════════════════════════ */
export function PlayerProfileSections({
  player,
  profile,
  profileReady,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
  profileReady: boolean
}) {
  if (!profileReady) {
    return (
      <div
        style={{
          background: VAR.bg1,
          border: `1px solid ${VAR.border}`,
          borderRadius: "var(--r-md)",
          padding: "16px 12px",
          fontFamily: VAR.mono,
          fontSize: 10,
          color: VAR.faint,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ animation: "pulse-glow 1.8s ease-in-out infinite", display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--green)" }} />
        Loading profile…
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <RankingHeaderSection player={player} profile={profile} />
      <SkillBreakdownSection player={player} profile={profile} />
      <RollingFormSection profile={profile} />
      <CourseEventSection profile={profile} />
      <BettingSection profile={profile} />
    </div>
  )
}

/* ── Legacy exports still used by other pages ───────────────────────── */
export function ComponentTable({
  title,
  components,
}: {
  title: string
  components?: Record<string, number>
}) {
  const entries = Object.entries(components ?? {})
  return (
    <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", padding: "10px 12px" }}>
      <div style={{ fontFamily: VAR.mono, fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.muted, marginBottom: 8 }}>
        {title}
      </div>
      {entries.length ? (
        entries.map(([key, value]) => (
          <StatRow key={key} label={key.replaceAll("_", " ")} value={formatNumber(value, 2)} tone={toneFn(value)} />
        ))
      ) : (
        <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint }}>No detail available.</div>
      )}
    </div>
  )
}

export function MetricsCategoryTable({
  title,
  categories,
}: {
  title: string
  categories?: Record<string, Record<string, number | string | null>>
}) {
  const entries = Object.entries(categories ?? {})
  return (
    <div style={{ background: VAR.bg1, border: `1px solid ${VAR.border}`, borderRadius: "var(--r-md)", padding: "10px 12px" }}>
      <div style={{ fontFamily: VAR.mono, fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: VAR.muted, marginBottom: 8 }}>
        {title}
      </div>
      {entries.length ? (
        entries.map(([cat, vals]) => (
          <div key={cat} style={{ marginBottom: 10 }}>
            <div style={{ fontFamily: VAR.mono, fontSize: 8, letterSpacing: "0.14em", textTransform: "uppercase", color: VAR.faint, marginBottom: 4 }}>{cat}</div>
            {Object.entries(vals).map(([k, v]) => (
              <StatRow
                key={k}
                label={k.replaceAll("_", " ")}
                value={typeof v === "number" ? formatNumber(v, 2) : String(v ?? "—")}
                tone={typeof v === "number" ? toneFn(v) : undefined}
              />
            ))}
          </div>
        ))
      ) : (
        <div style={{ fontFamily: VAR.mono, fontSize: 9, color: VAR.faint }}>No metrics available.</div>
      )}
    </div>
  )
}
