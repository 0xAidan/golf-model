import { useMemo, useState } from "react"
import { ChevronDown, Flag, TrendingUp } from "lucide-react"

import { SparklineChart } from "@/components/charts"
import { MetricTile } from "@/components/shell"
import { formatNumber } from "@/lib/format"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

type RollingWindow = "10" | "25" | "50"
type BenchmarkTier = "tour_avg" | "top50" | "top10"

const WINDOW_OPTIONS: RollingWindow[] = ["10", "25", "50"]
const BENCHMARK_OPTIONS: BenchmarkTier[] = ["tour_avg", "top50", "top10"]
const BENCHMARK_LABELS: Record<BenchmarkTier, string> = {
  tour_avg: "Tour Avg",
  top50: "Top 50%",
  top10: "Top 10",
}

function ProfileSection({
  title,
  subtitle,
  defaultOpen = true,
  children,
}: {
  title: string
  subtitle: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  return (
    <details className="rounded-2xl border border-white/8 bg-black/20" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-left">
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          <p className="text-xs text-slate-400">{subtitle}</p>
        </div>
        <ChevronDown className="h-4 w-4 text-slate-500 transition group-open:rotate-180" />
      </summary>
      <div className="space-y-4 border-t border-white/8 px-4 py-4">{children}</div>
    </details>
  )
}

function statTone(value?: number | null): "default" | "positive" | "warning" {
  if (value == null) return "default"
  if (value > 0) return "positive"
  if (value < 0) return "warning"
  return "default"
}

function formatSigned(value?: number | null, digits = 2): string {
  if (value == null) return "--"
  const sign = value > 0 ? "+" : ""
  return `${sign}${value.toFixed(digits)}`
}

function RankingHeaderSection({
  player,
  profile,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
}) {
  return (
    <ProfileSection
      title="Profile Header"
      subtitle="Live ranking position, confidence, and field context."
    >
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label="Model rank" value={`#${player.rank}`} />
        <MetricTile label="Composite" value={formatNumber(player.composite, 1)} />
        <MetricTile
          label="Course confidence"
          value={formatNumber(player.course_confidence, 2)}
          detail={`Course rounds: ${player.course_rounds ?? profile?.header?.course_rounds_tracked ?? 0}`}
        />
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="DG rank" value={formatNumber(profile?.header?.dg_rank, 0)} />
        <MetricTile label="OWGR rank" value={formatNumber(profile?.header?.owgr_rank, 0)} />
        <MetricTile label="DG skill est." value={formatNumber(profile?.header?.dg_skill_estimate, 2)} />
        <MetricTile
          label="Field size"
          value={String(profile?.header?.field_size ?? "--")}
          detail={String(profile?.header?.field_status ?? "field status unavailable")}
        />
      </div>
    </ProfileSection>
  )
}

function SkillBreakdownSection({
  player,
  profile,
}: {
  player: CompositePlayer
  profile?: PlayerProfile
}) {
  const primary = profile?.skill_breakdown?.primary ?? []
  const approachBuckets = profile?.skill_breakdown?.approach_buckets ?? []
  const componentDeltas = profile?.skill_breakdown?.component_deltas ?? []
  const bestArea = profile?.skill_breakdown?.summary?.best_area
  const weakestArea = profile?.skill_breakdown?.summary?.weakest_area

  return (
    <ProfileSection
      title="Skill Breakdown"
      subtitle="DG skills, approach buckets, and component-level edges."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <MetricTile
          label="Best area"
          value={bestArea ? `${bestArea.label}: ${formatSigned(bestArea.value, 3)}` : "--"}
          tone={statTone(bestArea?.value)}
        />
        <MetricTile
          label="Weakest area"
          value={weakestArea ? `${weakestArea.label}: ${formatSigned(weakestArea.value, 3)}` : "--"}
          tone={statTone(weakestArea?.value)}
        />
      </div>

      {primary.length ? (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {primary.map((entry) => (
            <MetricTile
              key={entry.key}
              label={entry.label}
              value={formatSigned(entry.value, 3)}
              tone={statTone(entry.value)}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No DG skill breakdown is available for this player yet.</p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <ComponentTable
          title="Component deltas"
          components={Object.fromEntries(componentDeltas.map((entry) => [entry.label, entry.value]))}
        />
        <ComponentTable
          title="Approach buckets"
          components={Object.fromEntries(approachBuckets.slice(0, 8).map((entry) => [entry.label, entry.value]))}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <ComponentTable title="Course components" components={player.details?.course_components} />
        <ComponentTable title="Form components" components={player.details?.form_components} />
        <ComponentTable title="Momentum windows" components={player.details?.momentum_windows} />
      </div>
    </ProfileSection>
  )
}

function RollingFormSection({
  profile,
}: {
  profile?: PlayerProfile
}) {
  const [windowKey, setWindowKey] = useState<RollingWindow>("25")
  const [benchmarkKey, setBenchmarkKey] = useState<BenchmarkTier>("tour_avg")

  const rolling = profile?.rolling_form
  const trendValues = useMemo(() => {
    if (rolling?.trend_series?.length) {
      return rolling.trend_series
    }
    return (profile?.recent_rounds ?? [])
      .map((round) => Number(round.sg_total ?? 0))
      .reverse()
  }, [profile?.recent_rounds, rolling?.trend_series])

  const selectedWindowValue = rolling?.windows?.[windowKey] ?? null
  const benchmarkValue = rolling?.benchmarks?.[benchmarkKey]?.[windowKey] ?? null
  const edgeVsBenchmark =
    selectedWindowValue != null && benchmarkValue != null
      ? selectedWindowValue - benchmarkValue
      : null

  return (
    <ProfileSection
      title="Rolling Form"
      subtitle="Window-based SG trend versus selectable benchmark tiers."
    >
      <div className="flex flex-wrap items-center gap-2">
        {WINDOW_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            className={`rounded-xl border px-3 py-1.5 text-xs font-medium ${
              option === windowKey
                ? "border-cyan-300/70 bg-cyan-400/20 text-cyan-100"
                : "border-white/12 text-slate-300 hover:bg-white/6"
            }`}
            onClick={() => setWindowKey(option)}
            aria-label={`Show ${option} round view`}
          >
            {option} rounds
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {BENCHMARK_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            className={`rounded-xl border px-3 py-1.5 text-xs font-medium ${
              option === benchmarkKey
                ? "border-emerald-300/70 bg-emerald-400/20 text-emerald-100"
                : "border-white/12 text-slate-300 hover:bg-white/6"
            }`}
            onClick={() => setBenchmarkKey(option)}
            aria-label={`Compare against ${BENCHMARK_LABELS[option]}`}
          >
            {BENCHMARK_LABELS[option]}
          </button>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label={`Player SG (${windowKey})`} value={formatSigned(selectedWindowValue, 3)} tone={statTone(selectedWindowValue)} />
        <MetricTile
          label={`${BENCHMARK_LABELS[benchmarkKey]} SG`}
          value={formatSigned(benchmarkValue, 3)}
          tone={statTone(benchmarkValue)}
        />
        <MetricTile
          label="Edge vs benchmark"
          value={formatSigned(edgeVsBenchmark, 3)}
          detail={`Short vs medium delta: ${formatSigned(profile?.rolling_form?.summary?.delta_short_vs_medium, 3)}`}
          tone={statTone(edgeVsBenchmark)}
        />
      </div>
      {trendValues.length ? (
        <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
          <div className="mb-2 flex items-center gap-2 text-slate-300">
            <TrendingUp className="h-4 w-4 text-cyan-200" />
            <span className="text-sm font-medium">SG trend series</span>
          </div>
          <SparklineChart values={trendValues} color="#5eead4" />
        </div>
      ) : (
        <p className="text-sm text-slate-400">Rolling trend data is not available yet.</p>
      )}
    </ProfileSection>
  )
}

function CourseEventContextSection({ profile }: { profile?: PlayerProfile }) {
  const recentStarts = profile?.course_event_context?.recent_starts ?? []
  const courseSummary = profile?.course_event_context?.course_summary
  const recentSummary = profile?.course_event_context?.recent_summary
  const courseValues = (profile?.course_history ?? [])
    .map((round) => Number(round.sg_total ?? 0))
    .reverse()

  return (
    <ProfileSection
      title="Course/Event Context"
      subtitle="Recent starts and course comfort trends from stored rounds."
    >
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Events tracked" value={String(recentSummary?.events_tracked ?? 0)} />
        <MetricTile label="Made cuts" value={String(recentSummary?.made_cuts ?? 0)} />
        <MetricTile label="Recent avg SG" value={formatSigned(recentSummary?.avg_sg_total, 3)} tone={statTone(recentSummary?.avg_sg_total)} />
        <MetricTile label="Course avg SG" value={formatSigned(courseSummary?.avg_sg_total, 3)} tone={statTone(courseSummary?.avg_sg_total)} />
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
      {recentStarts.length ? (
        <div className="space-y-2">
          {recentStarts.slice(0, 6).map((event, index) => (
            <div
              key={`${event.event_name ?? "event"}-${index}`}
              className="flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-black/20 px-3 py-2"
            >
              <div>
                <p className="text-sm font-medium text-white">{event.event_name ?? "Unknown event"}</p>
                <p className="text-xs text-slate-500">{event.event_completed ?? "Date unavailable"}</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-slate-200">{event.fin_text ?? "--"}</p>
                <p className="text-xs text-slate-500">Avg SG {formatSigned(event.avg_sg_total, 3)}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No event history is available for this player yet.</p>
      )}
    </ProfileSection>
  )
}

function BettingContextSection({ profile }: { profile?: PlayerProfile }) {
  const linkedBets = profile?.linked_bets ?? []
  const summary = profile?.betting_context?.summary

  return (
    <ProfileSection
      title="Betting Context"
      subtitle="How this player appears in current tournament card exposures."
    >
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label="Linked bets" value={String(summary?.linked_bet_count ?? linkedBets.length)} />
        <MetricTile label="Average EV" value={formatSigned(summary?.average_ev, 3)} tone={statTone(summary?.average_ev)} />
        <MetricTile label="High-confidence bets" value={String(summary?.high_confidence_count ?? 0)} />
      </div>
      {linkedBets.length ? (
        <div className="space-y-3">
          {linkedBets.slice(0, 6).map((bet, index) => (
            <div key={`${bet.bet_type ?? "bet"}-${index}`} className="flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-black/20 px-3 py-3">
              <div>
                <p className="text-sm font-medium text-white">{bet.bet_type ?? "bet"}</p>
                <p className="text-xs text-slate-500">
                  {bet.player_display}
                  {bet.opponent_display ? ` vs ${bet.opponent_display}` : ""}
                </p>
                {bet.reasoning ? <p className="mt-1 text-xs text-slate-500">{bet.reasoning}</p> : null}
              </div>
              <div className="text-right">
                <p className="text-sm text-cyan-200">{bet.market_odds ?? "--"}</p>
                <p className="text-xs text-slate-500">
                  EV {formatSigned(bet.ev, 3)} · {bet.confidence ?? "quant"}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-400">No linked bets are available for this player in the current run.</p>
      )}
      <MetricsCategoryTable title="Current market context" categories={profile?.current_metrics} />
    </ProfileSection>
  )
}

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
      <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-6 text-sm text-slate-400">
        Loading richer profile context...
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <RankingHeaderSection player={player} profile={profile} />
      <SkillBreakdownSection player={player} profile={profile} />
      <RollingFormSection profile={profile} />
      <CourseEventContextSection profile={profile} />
      <BettingContextSection profile={profile} />
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

export function MetricsCategoryTable({
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
