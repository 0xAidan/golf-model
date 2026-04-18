import type {
  FlattenedSecondaryBet,
  LiveMatchupRow,
  LiveRefreshSnapshot,
  LiveTournamentSnapshot,
  MatchupBet,
  PredictionRunResponse,
  SecondaryBet,
} from "./types"

export const NON_BOOK_SOURCES = new Set(["datagolf"])

export function normalizeSportsbook(value?: string | null): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
}

function normalizeNameForUi(value?: string): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

function isDisplayBook(value?: string | null): boolean {
  const normalized = normalizeSportsbook(value)
  return normalized.length > 0 && !NON_BOOK_SOURCES.has(normalized)
}

function normalizeOddsDisplay(oddsValue: unknown, fallbackOdds?: unknown): string {
  const primaryMissing =
    oddsValue === null
    || oddsValue === undefined
    || (typeof oddsValue === "string" && oddsValue.trim() === "")
  const candidate = primaryMissing ? fallbackOdds : oddsValue
  if (candidate === null || candidate === undefined || candidate === "") {
    return "--"
  }

  if (typeof candidate === "number" && Number.isFinite(candidate)) {
    if (candidate > 0) {
      return `+${candidate}`
    }
    return String(candidate)
  }

  const asText = String(candidate).trim()
  if (!asText) {
    return "--"
  }
  return asText
}

function hydrateLegacyMatchups(matchups: LiveMatchupRow[] | undefined): MatchupBet[] {
  return (matchups ?? []).map((row) => {
    const ev = Number(row.ev ?? 0)
    const modelWinProb = Number(row.model_prob ?? 0.5)
    const impliedProb = modelWinProb > 0 ? 1 / (1 + ev / modelWinProb) : 0.5
    const pickKey = row.player_key ?? normalizeNameForUi(row.player)
    const opponentKey = row.opponent_key ?? normalizeNameForUi(row.opponent)

    return {
      pick: row.player,
      pick_key: pickKey,
      opponent: row.opponent,
      opponent_key: opponentKey,
      odds: String(row.market_odds ?? "--"),
      book: normalizeSportsbook(row.bookmaker) || undefined,
      model_win_prob: modelWinProb,
      implied_prob: impliedProb,
      ev,
      ev_pct: `${(ev * 100).toFixed(1)}%`,
      composite_gap: Number(row.composite_gap ?? 0),
      form_gap: Number(row.form_gap ?? 0),
      course_fit_gap: Number(row.course_fit_gap ?? 0),
      reason: "Hydrated from always-on snapshot",
      tier: row.tier,
      conviction: row.conviction != null ? Number(row.conviction) : undefined,
      pick_momentum: row.pick_momentum != null ? Number(row.pick_momentum) : undefined,
      opp_momentum: row.opp_momentum != null ? Number(row.opp_momentum) : undefined,
      momentum_aligned: row.momentum_aligned,
      market_type: row.market_type,
    }
  })
}

function normalizeSnapshotMatchupRows(rows: MatchupBet[]): MatchupBet[] {
  return rows
    .filter((row) => isDisplayBook(row.book))
    .map((row) => {
      const ev = Number(row.ev ?? 0)
      const modelWinProb = Number(row.model_win_prob ?? 0.5)
      const impliedProb = row.implied_prob != null
        ? Number(row.implied_prob)
        : modelWinProb > 0
          ? 1 / (1 + ev / modelWinProb)
          : 0.5
      const normalizedBook = normalizeSportsbook(row.book) || undefined

      return {
        ...row,
        pick: row.pick ?? "",
        pick_key: row.pick_key ?? normalizeNameForUi(row.pick),
        opponent: row.opponent ?? "",
        opponent_key: row.opponent_key ?? normalizeNameForUi(row.opponent),
        odds: String(row.odds ?? "--"),
        book: normalizedBook,
        model_win_prob: modelWinProb,
        implied_prob: impliedProb,
        ev,
        ev_pct: row.ev_pct ?? `${(ev * 100).toFixed(1)}%`,
        composite_gap: Number(row.composite_gap ?? 0),
        form_gap: Number(row.form_gap ?? 0),
        course_fit_gap: Number(row.course_fit_gap ?? 0),
        reason: row.reason ?? "Hydrated from always-on snapshot",
        conviction: row.conviction != null ? Number(row.conviction) : undefined,
        pick_momentum: row.pick_momentum != null ? Number(row.pick_momentum) : undefined,
        opp_momentum: row.opp_momentum != null ? Number(row.opp_momentum) : undefined,
        stake_multiplier: row.stake_multiplier != null ? Number(row.stake_multiplier) : undefined,
      }
    })
    .sort((left, right) => right.ev - left.ev)
}

export function hydrateSnapshotMatchups(source: LiveTournamentSnapshot): MatchupBet[] {
  const seededRows = Array.isArray(source.matchup_bets)
    ? source.matchup_bets
    : source.matchup_bets === null
      ? []
      : hydrateLegacyMatchups(source.matchups)

  return normalizeSnapshotMatchupRows(seededRows)
}

export function hydrateSnapshotMatchupsAllBooks(source: LiveTournamentSnapshot): MatchupBet[] {
  const seededRows = Array.isArray(source.matchup_bets_all_books)
    ? source.matchup_bets_all_books
    : source.matchup_bets_all_books === null
      ? []
      : Array.isArray(source.matchup_bets)
        ? source.matchup_bets
        : source.matchup_bets === null
          ? []
          : hydrateLegacyMatchups(source.matchups)

  return normalizeSnapshotMatchupRows(seededRows)
}

export function hydrateSnapshotValueBets(source: LiveTournamentSnapshot): Record<string, SecondaryBet[]> {
  const hydrated: Record<string, SecondaryBet[]> = {}
  const rawValueBets =
    source.value_bets && typeof source.value_bets === "object"
      ? source.value_bets
      : {}

  for (const [market, bets] of Object.entries(rawValueBets)) {
    const rows = bets
      .filter((bet) => Boolean(bet.is_value) && isDisplayBook(bet.book ?? bet.best_book))
      .map((bet) => {
        const normalizedBook = normalizeSportsbook(bet.book ?? bet.best_book) || undefined
        const normalizedBestBook = normalizeSportsbook(bet.best_book) || undefined
        const ev = Number(bet.ev ?? 0)

        return {
          ...bet,
          player: bet.player ?? bet.player_display ?? "Unknown player",
          player_display: bet.player_display ?? bet.player ?? "Unknown player",
          odds: normalizeOddsDisplay(bet.odds, bet.best_odds),
          book: normalizedBook,
          best_book: normalizedBestBook,
          ev,
          ev_pct: bet.ev_pct ?? `${(ev * 100).toFixed(1)}%`,
          is_value: true,
        }
      })
      .sort((left, right) => right.ev - left.ev)

    if (rows.length > 0) {
      hydrated[market] = rows
    }
  }

  return hydrated
}

export function collectAvailableBooks(predictionRun: PredictionRunResponse | null): string[] {
  const names = new Set<string>()
  const matchupBookSource = predictionRun?.matchup_bets_all_books ?? predictionRun?.matchup_bets ?? []

  for (const matchup of matchupBookSource) {
    const normalized = normalizeSportsbook(matchup.book)
    if (normalized && !NON_BOOK_SOURCES.has(normalized)) {
      names.add(normalized)
    }
  }

  for (const bets of Object.values(predictionRun?.value_bets ?? {})) {
    for (const bet of bets) {
      if (!bet.is_value) continue
      const normalized = normalizeSportsbook(bet.book ?? bet.best_book)
      if (normalized && !NON_BOOK_SOURCES.has(normalized)) {
        names.add(normalized)
      }
    }
  }

  return Array.from(names).sort()
}

export function flattenSecondaryBets(predictionRun: PredictionRunResponse | null): FlattenedSecondaryBet[] {
  const entries = Object.entries(predictionRun?.value_bets ?? {})
  return entries
    .flatMap(([market, bets]) =>
      bets
        .filter((bet) => bet.is_value)
        .map((bet) => ({
          market,
          player: bet.player_display ?? bet.player ?? "Unknown player",
          player_display: bet.player_display ?? bet.player ?? "Unknown player",
          player_key: bet.player_key,
          odds: normalizeOddsDisplay(bet.odds, bet.best_odds),
          ev: bet.ev,
          confidence: bet.confidence,
          book: normalizeSportsbook(bet.book ?? bet.best_book),
        })),
    )
    .sort((left, right) => right.ev - left.ev)
}

export function buildHydratedPredictionRun(
  snapshot: LiveRefreshSnapshot | null,
  tab: "live" | "upcoming",
): PredictionRunResponse | null {
  if (!snapshot) {
    return null
  }

  const source =
    tab === "live"
      ? (snapshot.live_tournament ?? snapshot.upcoming_tournament)
      : (snapshot.upcoming_tournament ?? snapshot.live_tournament)

  return buildPredictionRunFromSection(source)
}

export function buildPredictionRunFromSection(
  source: LiveTournamentSnapshot | null | undefined,
): PredictionRunResponse | null {
  if (!source) {
    return null
  }

  const eligibility = source.eligibility
  if (eligibility && eligibility.verified === false) {
    const warning = [
      eligibility.summary ?? "Rankings withheld: field eligibility not verified.",
      eligibility.action ?? "",
    ]
      .filter(Boolean)
      .join(" ")
      .trim()
    return {
      status: "hydrated",
      event_name: source.event_name ?? "Event",
      course_name: source.course_name ?? "",
      field_size: source.field_size ?? 0,
      tournament_id: source.tournament_id,
      course_num: source.course_num,
      composite_results: [],
      matchup_bets: [],
      value_bets: {},
      errors: [warning],
      warnings: [warning],
    }
  }

  const rankings = source.live_rankings ?? source.rankings ?? []
  const matchupBets = hydrateSnapshotMatchups(source)
  const matchupBetsAllBooks = hydrateSnapshotMatchupsAllBooks(source)
  const valueBets = hydrateSnapshotValueBets(source)

  return {
    status: "hydrated",
    event_name: source.event_name ?? "Event",
    course_name: source.course_name ?? "",
    field_size: source.field_size ?? rankings.length,
    tournament_id: source.tournament_id,
    course_num: source.course_num,
    composite_results: rankings.map((row) => ({
      player_key: row.player_key ?? normalizeNameForUi(row.player),
      player_display: row.player,
      rank: Number(row.rank ?? 0),
      composite: Number(row.composite ?? 0),
      course_fit: Number(row.course_fit ?? 0),
      form: Number(row.form ?? 0),
      momentum: Number(row.momentum ?? 0),
      momentum_direction: row.momentum_direction,
      momentum_trend: row.momentum_trend != null ? Number(row.momentum_trend) : undefined,
      course_confidence: row.course_confidence != null ? Number(row.course_confidence) : undefined,
      course_rounds: row.course_rounds != null ? Number(row.course_rounds) : undefined,
      weather_adjustment: row.weather_adjustment != null ? Number(row.weather_adjustment) : undefined,
      availability: row.availability,
      form_flags: row.form_flags,
      form_notes: row.form_notes,
      details: row.details,
    })),
    matchup_bets: matchupBets,
    matchup_bets_all_books: matchupBetsAllBooks,
    value_bets: valueBets,
    warnings: ["Hydrated from snapshot history. Manual runs are still required for card export and full provenance details."],
  }
}
