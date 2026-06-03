import { NON_BOOK_SOURCES, normalizeSportsbook } from "./prediction-board"
import type { FailedMatchupCandidate, MatchupBet } from "./types"

export type MatchupExplorationFilters = {
  selectedBooks: Set<string> | string[]
  matchupSearch: string
  minEdge: number
}

function normalizePickKey(value?: string): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

function matchupRowKey(
  row: Pick<MatchupBet, "pick_key" | "opponent_key" | "book" | "pick" | "opponent">,
): string {
  const pickKey = row.pick_key || normalizePickKey(row.pick)
  const opponentKey = row.opponent_key || normalizePickKey(row.opponent)
  const book = normalizeSportsbook(row.book)
  return `${pickKey}|${opponentKey}|${book}`
}

function normalizeOddsForBet(odds: number | string | null | undefined): string {
  if (odds === null || odds === undefined || odds === "") {
    return "--"
  }
  if (typeof odds === "number" && Number.isFinite(odds)) {
    return odds > 0 ? `+${odds}` : String(odds)
  }
  const asText = String(odds).trim()
  return asText || "--"
}

function gateReasonLabel(code: string): string {
  const labels: Record<string, string> = {
    below_ev_threshold: "Below model EV threshold — use the min edge slider to include",
    dg_model_disagreement: "DataGolf / model disagreement",
  }
  return labels[code] ?? code.replaceAll("_", " ")
}

export function failedCandidateToMatchupBet(candidate: FailedMatchupCandidate): MatchupBet | null {
  if (candidate.ev === null || candidate.ev === undefined || !Number.isFinite(Number(candidate.ev))) {
    return null
  }

  const ev = Number(candidate.ev)
  const book = normalizeSportsbook(candidate.book)
  if (!book || NON_BOOK_SOURCES.has(book)) {
    return null
  }

  const modelWinProb = Number(candidate.model_win_prob ?? 0.5)
  const impliedProb =
    candidate.implied_prob !== null && candidate.implied_prob !== undefined
      ? Number(candidate.implied_prob)
      : modelWinProb > 0
        ? 1 / (1 + ev / modelWinProb)
        : 0.5

  return {
    pick: candidate.pick,
    pick_key: normalizePickKey(candidate.pick),
    opponent: candidate.opponent,
    opponent_key: normalizePickKey(candidate.opponent),
    odds: normalizeOddsForBet(candidate.odds),
    book,
    model_win_prob: modelWinProb,
    implied_prob: impliedProb,
    ev,
    ev_pct: candidate.ev_pct ?? `${(ev * 100).toFixed(1)}%`,
    composite_gap: Number(candidate.composite_gap ?? 0),
    form_gap: 0,
    course_fit_gap: 0,
    reason: gateReasonLabel(candidate.reason_code),
    explore_source: "candidate",
    gate_reason: candidate.reason_code,
    market_type: candidate.market_type,
  }
}

export function buildExplorableMatchupPool(
  cardRows: MatchupBet[],
  failedCandidates: FailedMatchupCandidate[] | undefined,
): MatchupBet[] {
  const byKey = new Map<string, MatchupBet>()

  for (const row of cardRows) {
    const book = normalizeSportsbook(row.book)
    if (book && NON_BOOK_SOURCES.has(book)) {
      continue
    }
    byKey.set(matchupRowKey(row), {
      ...row,
      explore_source: row.explore_source ?? "card",
    })
  }

  for (const candidate of failedCandidates ?? []) {
    const converted = failedCandidateToMatchupBet(candidate)
    if (!converted) {
      continue
    }
    const key = matchupRowKey(converted)
    if (!byKey.has(key)) {
      byKey.set(key, converted)
    }
  }

  return Array.from(byKey.values())
}

export function filterExplorableMatchups(
  pool: MatchupBet[],
  filters: MatchupExplorationFilters,
): MatchupBet[] {
  const bookSet =
    filters.selectedBooks instanceof Set
      ? filters.selectedBooks
      : new Set(filters.selectedBooks.map((book) => normalizeSportsbook(book)))
  const search = filters.matchupSearch.trim().toLowerCase()

  const filtered = pool.filter((matchup) => {
    const matchupBook = normalizeSportsbook(matchup.book)
    if (!matchupBook || NON_BOOK_SOURCES.has(matchupBook)) {
      return false
    }
    if (bookSet.size > 0 && !bookSet.has(matchupBook)) {
      return false
    }
    if (search && !`${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(search)) {
      return false
    }
    return Number.isFinite(matchup.ev) && matchup.ev >= filters.minEdge
  })

  return filtered.sort((left, right) => right.ev - left.ev)
}

export function filterMatchupsForExploration(
  cardRows: MatchupBet[],
  failedCandidates: FailedMatchupCandidate[] | undefined,
  filters: MatchupExplorationFilters,
): MatchupBet[] {
  const pool = buildExplorableMatchupPool(cardRows, failedCandidates)
  return filterExplorableMatchups(pool, filters)
}
