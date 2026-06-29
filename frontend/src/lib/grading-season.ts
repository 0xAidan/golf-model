import type {
  GradedTournamentSummary,
  GradingHistoryResponse,
  GradingSeasonEvent,
  GradingSeasonResponse,
} from "@/lib/types"

export const seasonLaneFromPickSource = (
  pickSource: "all" | "cockpit" | "lab",
): "all" | "cockpit" | "lab" => pickSource

export const seasonEventsToGradingHistory = (
  season: GradingSeasonResponse | undefined,
  pickSource: "all" | "cockpit" | "lab",
): GradingHistoryResponse => {
  if (!season) {
    return { tournaments: [] }
  }

  const tournaments: GradedTournamentSummary[] = season.events.map((event) => {
    if (pickSource === "all") {
      return {
        id: event.tournament_id ?? undefined,
        name: event.name,
        course: event.course,
        year: event.year,
        event_id: event.event_id,
        graded_pick_count: event.graded_pick_count,
        hits: event.hits,
        total_profit: event.total_profit,
        picks: event.picks,
        last_graded_at: event.last_graded_at,
        market_stats: event.market_stats,
      }
    }

    const lane = pickSource === "lab" ? event.lanes?.lab : event.lanes?.dashboard
    return {
      id: event.tournament_id ?? undefined,
      name: event.name,
      course: event.course,
      year: event.year,
      event_id: event.event_id,
      graded_pick_count: lane?.graded_pick_count ?? event.graded_pick_count,
      hits: lane?.hits ?? event.hits,
      total_profit: lane?.total_profit ?? event.total_profit,
      picks: lane?.picks ?? event.picks,
      last_graded_at: event.last_graded_at,
      market_stats: lane?.market_stats ?? event.market_stats,
      picks_count: lane?.inventory_count,
    }
  })

  const summary =
    pickSource === "lab"
      ? { combined: season.summary.lab, outrights: season.summary.lab, matchups: season.summary.lab }
      : pickSource === "cockpit"
        ? { combined: season.summary.dashboard, outrights: season.summary.dashboard, matchups: season.summary.dashboard }
        : undefined

  return { tournaments, summary }
}

export const laneStatusLabel = (status: string | undefined): string => {
  if (status === "graded") return "Graded"
  if (status === "card_recovered") return "Card recovered"
  if (status === "partial") return "Partial"
  if (status === "inventory_only") return "Inventory only"
  if (status === "rollup_only") return "Rollup only"
  if (status === "in_progress") return "In progress"
  if (status === "no_data") return "No data"
  return "—"
}

export const formatSeasonEventDate = (value: string | null | undefined): string => {
  if (!value) return ""
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed)
}

export const isSeasonEvent = (event: GradedTournamentSummary): event is GradingSeasonEvent =>
  "lanes" in event && event.lanes != null

const laneUngradedPositiveEv = (
  event: GradingSeasonEvent,
  pickSource: "all" | "cockpit" | "lab",
): number => {
  if (pickSource === "lab") {
    return event.lanes?.lab?.ungraded_positive_ev_count ?? 0
  }
  if (pickSource === "all") {
    return (
      (event.lanes?.dashboard?.ungraded_positive_ev_count ?? 0) +
      (event.lanes?.lab?.ungraded_positive_ev_count ?? 0)
    )
  }
  return event.lanes?.dashboard?.ungraded_positive_ev_count ?? 0
}

/** Sum +EV gaps only for events that have final results (post-completion). */
export const sumUngradedPositiveEvForCompletedEvents = (
  events: GradingSeasonEvent[],
  pickSource: "all" | "cockpit" | "lab",
): number =>
  events.reduce((total, event) => {
    if (!event.has_results) return total
    return total + laneUngradedPositiveEv(event, pickSource)
  }, 0)

export const pickLatestGradedSeasonEvent = (
  events: GradingSeasonEvent[],
  pickSource: "all" | "cockpit" | "lab",
): GradingSeasonEvent | null => {
  let best: GradingSeasonEvent | null = null
  let bestTs = Number.NEGATIVE_INFINITY
  for (const event of events) {
    const lane =
      pickSource === "lab"
        ? event.lanes?.lab
        : pickSource === "cockpit"
          ? event.lanes?.dashboard
          : null
    const graded =
      pickSource === "all"
        ? (event.lanes?.dashboard?.graded_pick_count ?? 0) +
          (event.lanes?.lab?.graded_pick_count ?? 0)
        : (lane?.graded_pick_count ?? event.graded_pick_count ?? 0)
    if (graded <= 0) continue
    const ts = event.last_graded_at ? Date.parse(event.last_graded_at) : Number.NaN
    if (Number.isNaN(ts) || ts < bestTs) continue
    bestTs = ts
    best = event
  }
  return best
}

/** Last N season events with graded picks, in chronological order for charts. */
export const recentGradedSeasonEventsForTrend = (
  events: GradingSeasonEvent[],
  pickSource: "all" | "cockpit" | "lab",
  limit = 8,
): GradingSeasonEvent[] => {
  const graded = events.filter((event) => {
    const lane =
      pickSource === "lab"
        ? event.lanes?.lab
        : pickSource === "cockpit"
          ? event.lanes?.dashboard
          : null
    const count =
      pickSource === "all"
        ? (event.lanes?.dashboard?.graded_pick_count ?? 0) +
          (event.lanes?.lab?.graded_pick_count ?? 0)
        : (lane?.graded_pick_count ?? event.graded_pick_count ?? 0)
    return count > 0
  })
  return graded.slice(-limit)
}
