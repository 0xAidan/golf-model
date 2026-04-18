type MatchupStateMessageInput = {
  state?: string
  reasonCodes?: Record<string, number>
  hasFilters: boolean
}

type ActiveMatchupFiltersInput = {
  selectedBooks: string[]
  matchupSearch: string
  minEdge: number
  defaultMinEdge: number
}

export function hasActiveMatchupFilters({
  selectedBooks,
  matchupSearch,
  minEdge,
  defaultMinEdge,
}: ActiveMatchupFiltersInput) {
  if (selectedBooks.length > 0) {
    return true
  }

  if (matchupSearch.trim().length > 0) {
    return true
  }

  return minEdge > defaultMinEdge
}

export function getMatchupStateMessage({
  state,
  reasonCodes,
  hasFilters,
}: MatchupStateMessageInput) {
  if (hasFilters) {
    return "No matchup rows match current book/search/min-EV filters."
  }
  if (state === "no_market_posted_yet") {
    return "No sportsbook matchup lines are posted yet for this context."
  }
  if (state === "market_available_no_edges") {
    return "Markets are available, but no rows currently pass model and EV thresholds."
  }
  if (state === "pipeline_error") {
    return "Matchup pipeline reported an error. Check runtime diagnostics."
  }
  if ((reasonCodes?.missing_composite_player ?? 0) > 0) {
    return "Matchup rows were received, but player mapping to model scores failed."
  }
  return "No matchup rows are available yet."
}
