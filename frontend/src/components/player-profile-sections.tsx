import { useMemo, useState } from "react"

import {
  SgSkillBarsChart,
  SgRollingChart,
  TournamentHistoryChart,
  SparklineChart,
} from "@/components/charts"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/feedback-state"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { formatNumber } from "@/lib/format"
import {
  buildProfileBetsColumns,
  buildProfileTournamentColumns,
} from "@/lib/player-profile-columns"
import {
  MATCHUP_TABLE_TOOLTIPS,
  PLAYER_PROFILE_STAT_TOOLTIPS,
  PROFILE_BETTING_SUMMARY_TOOLTIPS,
  PROFILE_CHART_LABEL_TOOLTIPS,
  PROFILE_COURSE_SUMMARY_TOOLTIPS,
  ROLLING_FORM_TILE_TOOLTIPS,
  ROLLING_UI_TOOLTIPS,
  SKILL_HIGHLIGHT_TOOLTIPS,
} from "@/lib/metric-tooltips"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"
import { cn } from "@/lib/utils"

type Tone = "positive" | "negative" | "neutral"

function toneFn(v?: number | null): Tone {
  if (v == null) return "neutral"
  return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"
}

function signed(v?: number | null, digits = 3): string {
  if (v == null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(digits)}`
}

function KpiRow({
  items,
}: {
  items: Array<{ label: string; value: string | React.ReactNode; tone?: Tone; sub?: string; title?: string }>
}) {
  return (
    <div className="profile-kpi-row">
      {items.map((item, i) => {
        const tip = item.title ?? PLAYER_PROFILE_STAT_TOOLTIPS[item.label]
        return (
          <div
            key={item.label}
            title={tip}
            className={cn("profile-kpi-row-cell", tip && "profile-kpi-row-cell--help")}
          >
            <span className="profile-kpi-row-label">{item.label}</span>
            <span className={cn("profile-kpi-row-value", `profile-metric-value--${item.tone ?? "neutral"}`)}>
              {item.value}
            </span>
            {item.sub ? <span className="profile-kpi-row-sub">{item.sub}</span> : null}
          </div>
        )
      })}
    </div>
  )
}

function StatRow({
  label,
  value,
  tone,
  title,
}: {
  label: string
  value: string | React.ReactNode
  tone?: Tone
  title?: string
}) {
  const tip = title ?? PLAYER_PROFILE_STAT_TOOLTIPS[label]
  return (
    <div title={tip} className={cn("profile-stat-row", tip && "profile-stat-row--help")}>
      <span className="profile-stat-row-label">{label}</span>
      <span className={cn("profile-stat-row-value", `profile-metric-value--${tone ?? "neutral"}`)}>{value}</span>
    </div>
  )
}

function ChartLabel({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <div title={title} className={cn("profile-chart-label", title && "profile-chart-label--help")}>
      {children}
    </div>
  )
}

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
  return (
    <div className="profile-pill-group">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onSelect(opt)}
          className={cn("profile-pill", `profile-pill--${color}`, opt === active && "profile-pill--active")}
        >
          {labels ? labels[opt] : opt}
        </button>
      ))}
    </div>
  )
}

function RankingHeaderSection({
  player,
  profile,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
}) {
  const dgRank = profile?.header?.dg_rank
  const owgr = profile?.header?.owgr_rank
  const skill = profile?.header?.dg_skill_estimate
  const form = player.form
  const course = player.course_fit
  const momentum = player.momentum

  return (
    <CollapsibleSection title="Player Overview" defaultOpen>
      <KpiRow
        items={[
          { label: "Model Rank", value: `#${player.rank}` },
          { label: "Composite", value: formatNumber(player.composite, 1), tone: "positive" },
          { label: "DG Rank", value: dgRank ? `#${dgRank}` : "—" },
          { label: "OWGR", value: owgr ? `#${owgr}` : "—" },
          {
            label: "DG Skill",
            value: skill ? formatNumber(skill, 2) : "—",
            tone: toneFn(skill),
          },
        ]}
      />
      <div className="profile-mini-grid-3">
        {[
          {
            label: "Course Fit",
            value: formatNumber(course, 1),
            tone: toneFn(course),
            sub: `${profile?.header?.course_rounds_tracked ?? player.course_rounds ?? 0} rounds tracked`,
          },
          {
            label: "Form",
            value: formatNumber(form, 1),
            tone: toneFn(form),
            sub: "recent SG signal",
          },
          {
            label: "Momentum",
            value: formatNumber(momentum, 1),
            tone: toneFn(momentum),
            sub: player.momentum_direction ?? "",
          },
        ].map((item) => (
          <div
            key={item.label}
            title={PLAYER_PROFILE_STAT_TOOLTIPS[item.label]}
            className="profile-mini-tile profile-mini-tile--help"
          >
            <div className="profile-mini-tile-label">{item.label}</div>
            <div className={cn("profile-mini-tile-value", `profile-metric-value--${item.tone}`)}>{item.value}</div>
            <div className="profile-mini-tile-sub">{item.sub}</div>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}

function SkillBreakdownSection({ player, profile }: { player: CompositePlayer; profile?: PlayerProfile }) {
  const primary = profile?.skill_breakdown?.primary ?? []
  const bestArea = profile?.skill_breakdown?.summary?.best_area
  const weakestArea = profile?.skill_breakdown?.summary?.weakest_area
  const skills = primary.map((s) => ({ label: s.label, value: s.value }))

  return (
    <CollapsibleSection title="SG Skill Profile" defaultOpen>
      {skills.length > 0 ? (
        <>
          {(bestArea || weakestArea) && (
            <div className="profile-highlight-grid">
              {bestArea ? (
                <div className="profile-highlight profile-highlight--pos" title={SKILL_HIGHLIGHT_TOOLTIPS.strength}>
                  <div className="profile-highlight-label">▲ Strength</div>
                  <div className="profile-highlight-value">
                    {bestArea.label} <span className="text-primary">{signed(bestArea.value)}</span>
                  </div>
                </div>
              ) : null}
              {weakestArea ? (
                <div className="profile-highlight profile-highlight--neg" title={SKILL_HIGHLIGHT_TOOLTIPS.weakness}>
                  <div className="profile-highlight-label">▼ Weakness</div>
                  <div className="profile-highlight-value">
                    {weakestArea.label} <span className="text-danger">{signed(weakestArea.value)}</span>
                  </div>
                </div>
              ) : null}
            </div>
          )}
          <ChartLabel title={PROFILE_CHART_LABEL_TOOLTIPS.sgPerRoundBars}>SG Per Round vs Tour Average (0.000)</ChartLabel>
          <SgSkillBarsChart skills={skills} height={Math.max(120, skills.length * 28 + 16)} />
        </>
      ) : (
        <>
          <ChartLabel title={PROFILE_CHART_LABEL_TOOLTIPS.modelScoreComponents}>Model Score Components</ChartLabel>
          <SgSkillBarsChart
            skills={Object.entries(player.details?.course_components ?? {}).map(([k, v]) => ({
              label: k.replaceAll("_", " "),
              value: v,
            }))}
            height={120}
          />
          <p className="profile-faint-note">DG skill breakdown not yet available — showing model score components.</p>
        </>
      )}
    </CollapsibleSection>
  )
}

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
    return (profile?.recent_rounds ?? []).map((r) => Number(r.sg_total ?? 0)).reverse()
  }, [rolling, profile?.recent_rounds])

  const windowVal = rolling?.windows?.[window] ?? null
  const benchVal = rolling?.benchmarks?.[bench]?.[window] ?? null
  const edgeVsBench = windowVal != null && benchVal != null ? windowVal - benchVal : null
  const shortVsMed = rolling?.summary?.delta_short_vs_medium

  return (
    <CollapsibleSection title="Rolling Form" defaultOpen>
      <div className="profile-pill-toolbar">
        <div>
          <div title={ROLLING_UI_TOOLTIPS.windowPills} className="profile-pill-toolbar-label profile-pill-toolbar-label--help">
            Window
          </div>
          <PillGroup
            options={WINDOW_OPTS}
            active={window}
            color="green"
            onSelect={setWindow}
            labels={{ "10": "L10", "25": "L25", "50": "L50" } as Record<RollingWindow, string>}
          />
        </div>
        <div>
          <div title={ROLLING_UI_TOOLTIPS.benchmarkPills} className="profile-pill-toolbar-label profile-pill-toolbar-label--help">
            Benchmark
          </div>
          <PillGroup options={BENCH_OPTS} labels={BENCH_LABELS} active={bench} color="gold" onSelect={setBench} />
        </div>
      </div>

      <div className="profile-mini-grid-3 profile-mini-grid-3--spaced">
        {[
          {
            label: `Avg SG (L${window})`,
            value: signed(windowVal),
            tone: toneFn(windowVal),
            sub: "strokes gained / round",
            title: ROLLING_FORM_TILE_TOOLTIPS.avgSgWindow,
          },
          {
            label: `${BENCH_LABELS[bench]} SG`,
            value: signed(benchVal),
            tone: "neutral" as Tone,
            sub: "benchmark",
            title: ROLLING_FORM_TILE_TOOLTIPS.benchmarkSg,
          },
          {
            label: "Edge vs Bench",
            value: signed(edgeVsBench),
            tone: toneFn(edgeVsBench),
            sub: shortVsMed != null ? `Δ short/med: ${signed(shortVsMed, 3)}` : "",
            title: ROLLING_FORM_TILE_TOOLTIPS.edgeVsBench,
          },
        ].map((item) => (
          <div key={item.label} title={item.title} className="profile-mini-tile profile-mini-tile--help">
            <div className="profile-mini-tile-label">{item.label}</div>
            <div className={cn("profile-mini-tile-value profile-mini-tile-value--lg", `profile-metric-value--${item.tone}`)}>
              {item.value}
            </div>
            {item.sub ? <div className="profile-mini-tile-sub">{item.sub}</div> : null}
          </div>
        ))}
      </div>

      <ChartLabel title={PROFILE_CHART_LABEL_TOOLTIPS.sgRoundTrend}>
        SG / Round Trend (oldest → newest, {trendValues.length} rounds)
      </ChartLabel>
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
    </CollapsibleSection>
  )
}

function CourseEventSection({ profile }: { profile?: PlayerProfile }) {
  const recentStarts = profile?.course_event_context?.recent_starts ?? []
  const recentSummary = profile?.course_event_context?.recent_summary
  const courseSummary = profile?.course_event_context?.course_summary
  const courseValues = (profile?.course_history ?? [])
    .map((r) => Number(r.sg_total ?? 0))
    .filter((v) => !Number.isNaN(v))
    .reverse()

  const chartEvents = recentStarts.map((s) => ({
    event_name: s.event_name ?? "Unknown",
    avg_sg_total: s.avg_sg_total ?? null,
    fin_text: s.fin_text,
  }))

  const tournamentColumns = useMemo(() => buildProfileTournamentColumns(), [])

  return (
    <CollapsibleSection title="Recent Tournament History" defaultOpen>
      <div className="profile-mini-grid-4">
        {[
          { label: "Events Tracked", value: String(recentSummary?.events_tracked ?? 0), title: PROFILE_COURSE_SUMMARY_TOOLTIPS["Events Tracked"] },
          { label: "Cuts Made", value: String(recentSummary?.made_cuts ?? 0), title: PROFILE_COURSE_SUMMARY_TOOLTIPS["Cuts Made"] },
          { label: "Recent Avg SG", value: signed(recentSummary?.avg_sg_total), tone: toneFn(recentSummary?.avg_sg_total), title: PROFILE_COURSE_SUMMARY_TOOLTIPS["Recent Avg SG"] },
          { label: "Course Avg SG", value: signed(courseSummary?.avg_sg_total), tone: toneFn(courseSummary?.avg_sg_total), title: PROFILE_COURSE_SUMMARY_TOOLTIPS["Course Avg SG"] },
        ].map((item) => (
          <div key={item.label} title={item.title} className="profile-mini-tile profile-mini-tile--help">
            <div className="profile-mini-tile-label">{item.label}</div>
            <div className={cn("profile-mini-tile-value", item.tone && `profile-metric-value--${item.tone}`)}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {chartEvents.length > 0 ? (
        <>
          <ChartLabel title={PROFILE_CHART_LABEL_TOOLTIPS.avgSgByEvent}>Avg SG by Event (most recent right)</ChartLabel>
          <TournamentHistoryChart events={chartEvents} height={150} />
        </>
      ) : null}

      {courseValues.length > 0 ? (
        <div className="profile-chart-block">
          <ChartLabel title={PROFILE_CHART_LABEL_TOOLTIPS.courseHistorySpark}>Course History SG Trend</ChartLabel>
          <SparklineChart values={courseValues} color="var(--green)" height={70} />
        </div>
      ) : null}

      {recentStarts.length > 0 ? (
        <div className="profile-table-block" data-testid="players-profile-tournaments">
          <ProDataGrid
            data={recentStarts.slice(0, 8)}
            columns={tournamentColumns}
            density="compact"
            getRowId={(row) => `${row.event_name ?? "e"}-${row.event_completed ?? ""}`}
            testId="players-profile-tournaments-grid"
          />
        </div>
      ) : null}
    </CollapsibleSection>
  )
}

function BettingSection({ profile }: { profile?: PlayerProfile }) {
  const bets = profile?.linked_bets ?? []
  const summary = profile?.betting_context?.summary
  const betColumns = useMemo(() => buildProfileBetsColumns(), [])

  return (
    <CollapsibleSection title="Betting Context" defaultOpen={false}>
      <div className="profile-mini-grid-3 profile-mini-grid-3--spaced">
        {[
          { label: "Linked Bets", value: String(summary?.linked_bet_count ?? bets.length), title: PROFILE_BETTING_SUMMARY_TOOLTIPS["Linked Bets"] },
          { label: "Avg EV", value: signed(summary?.average_ev), tone: toneFn(summary?.average_ev), title: PROFILE_BETTING_SUMMARY_TOOLTIPS["Avg EV"] },
          { label: "High Confidence", value: String(summary?.high_confidence_count ?? 0), title: PROFILE_BETTING_SUMMARY_TOOLTIPS["High Confidence"] },
        ].map((item) => (
          <div key={item.label} title={item.title} className="profile-mini-tile profile-mini-tile--help">
            <div className="profile-mini-tile-label">{item.label}</div>
            <div className={cn("profile-mini-tile-value profile-mini-tile-value--lg", item.tone && `profile-metric-value--${item.tone}`)}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
      {bets.length > 0 ? (
        <div className="profile-table-block" data-testid="players-profile-bets">
          <ProDataGrid
            data={bets.slice(0, 6)}
            columns={betColumns}
            density="compact"
            getRowId={(row) => `${row.bet_type ?? "b"}-${row.player_display ?? ""}-${row.market_odds ?? ""}`}
            testId="players-profile-bets-grid"
          />
        </div>
      ) : (
        <div className="profile-faint-note">No linked bets in current run.</div>
      )}
    </CollapsibleSection>
  )
}

export function PlayerProfileSections({
  player,
  profile,
  profileState,
  errorMessage,
  onRetry,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
  profileState: "loading" | "ready" | "error" | "unavailable"
  errorMessage?: string
  onRetry?: () => void
}) {
  if (profileState === "loading") {
    return <LoadingState message="Loading profile…" className="profile-state-card profile-state-card--loading" />
  }

  if (profileState === "error") {
    return (
      <ErrorState
        message={`Profile failed to load. ${errorMessage ?? "Please retry."}`}
        onRetry={onRetry}
        className="profile-state-card"
      />
    )
  }

  if (profileState !== "ready" || !profile) {
    return (
      <EmptyState
        message="Profile unavailable for this event context."
        className="profile-state-card"
      />
    )
  }

  return (
    <div className="profile-sections-stack">
      <RankingHeaderSection player={player} profile={profile} />
      <SkillBreakdownSection player={player} profile={profile} />
      <RollingFormSection profile={profile} />
      <CourseEventSection profile={profile} />
      <BettingSection profile={profile} />
    </div>
  )
}

export function ComponentTable({
  title,
  components,
}: {
  title: string
  components?: Record<string, number>
}) {
  const entries = Object.entries(components ?? {})
  return (
    <div className="profile-panel-card profile-panel-card--compact">
      <div className="profile-panel-card-title">{title}</div>
      {entries.length ? (
        entries.map(([key, value]) => (
          <StatRow key={key} label={key.replaceAll("_", " ")} value={formatNumber(value, 2)} tone={toneFn(value)} />
        ))
      ) : (
        <div className="profile-faint-note">No detail available.</div>
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
    <div className="profile-panel-card profile-panel-card--compact">
      <div className="profile-panel-card-title">{title}</div>
      {entries.length ? (
        entries.map(([cat, vals]) => (
          <div key={cat} className="profile-metrics-cat">
            <div className="profile-metrics-cat-label">{cat}</div>
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
        <div className="profile-faint-note">No metrics available.</div>
      )}
    </div>
  )
}
