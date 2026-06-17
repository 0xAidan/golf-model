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
