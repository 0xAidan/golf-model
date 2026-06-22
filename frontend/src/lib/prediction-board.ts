import type {
  FlattenedSecondaryBet,
  HydrationSectionKey,
  LiveMatchupRow,
  LiveRefreshSnapshot,
  LiveTournamentSnapshot,
  MatchupBet,
  PredictionRunResponse,
  SecondaryBet,
} from "./types"

export type { HydrationSectionKey }

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
        is_new_live_opportunity: Boolean(row.is_new_live_opportunity),
        is_new_since_last_snapshot: Boolean(row.is_new_since_last_snapshot),
        is_material_ev_increase: Boolean(row.is_material_ev_increase),
        first_seen_at: row.first_seen_at,
        live_bettable: row.live_bettable,
        market_provenance: row.market_provenance,
        availability_reason: row.availability_reason,
        line_seen_at: row.line_seen_at,
        last_seen_tick: row.last_seen_tick,
      }
    })
    .sort((left, right) => right.ev - left.ev)
}

export function hydrateSnapshotMatchups(
  source: LiveTournamentSnapshot,
  options?: { liveActionableOnly?: boolean },
): MatchupBet[] {
  const seededRows = Array.isArray(source.matchup_bets)
    ? source.matchup_bets
    : source.matchup_bets === null
      ? []
      : hydrateLegacyMatchups(source.matchups)

  const rows = normalizeSnapshotMatchupRows(seededRows)
  if (options?.liveActionableOnly) {
    return rows.filter((row) => row.live_bettable === true)
  }
  return rows
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
          is_new_live_opportunity: Boolean(bet.is_new_live_opportunity),
          is_material_ev_increase: Boolean(bet.is_material_ev_increase),
          first_seen_at: bet.first_seen_at,
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

/**
 * Books the pipeline supports, mirroring `src/config.py::SUPPORTED_BOOKS`. Used as
 * the final fallback so the book filter chips always render even when the current
 * board has zero qualifying edges (the regression fixed in the engine-scale Wave 1).
 */
export const SUPPORTED_BOOKS = [
  "draftkings",
  "fanduel",
  "betmgm",
  "caesars",
  "bet365",
  "pointsbet",
  "betrivers",
  "fanatics",
] as const

/**
 * Books offered in the filter UI. Unions books actually present on the run with the
 * snapshot's `diagnostics.books_seen` (every book the pipeline saw this tick, even
 * when no edge qualified), then falls back to SUPPORTED_BOOKS so the control never
 * disappears. `extraBooksSeen` is typically `section.diagnostics.books_seen`.
 */
export function collectBooksForFilter(
  predictionRun: PredictionRunResponse | null,
  extraBooksSeen?: string[] | null,
): string[] {
  const names = new Set<string>(collectAvailableBooks(predictionRun))
  for (const book of extraBooksSeen ?? []) {
    const normalized = normalizeSportsbook(book)
    if (normalized && !NON_BOOK_SOURCES.has(normalized)) {
      names.add(normalized)
    }
  }
  if (names.size === 0) {
    for (const book of SUPPORTED_BOOKS) {
      names.add(book)
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
          is_new_live_opportunity: Boolean(bet.is_new_live_opportunity),
          is_material_ev_increase: Boolean(bet.is_material_ev_increase),
          first_seen_at: bet.first_seen_at,
        })),
    )
    .sort((left, right) => right.ev - left.ev)
}

export type HydrationOptions = {
  /** When true, prefer live_player_board rows over rankings (live mode only). */
  preferLivePlayerBoard?: boolean
  hydrationSection?: HydrationSectionKey
}

export function buildHydratedPredictionRun(
  snapshot: LiveRefreshSnapshot | null,
  tab: "live" | "upcoming",
): PredictionRunResponse | null {
  if (!snapshot) {
    return null
  }

  const liveId = snapshot.live_tournament?.source_event_id
  const upcomingId = snapshot.upcoming_tournament?.source_event_id
  const sameEventContext = Boolean(liveId && upcomingId && liveId === upcomingId)

  let source: LiveTournamentSnapshot | null | undefined
  let hydrationSection: HydrationSectionKey

  if (tab === "live") {
    if (snapshot.live_tournament) {
      source = snapshot.live_tournament
      hydrationSection = "live"
    } else if (snapshot.upcoming_tournament && !sameEventContext) {
      source = snapshot.upcoming_tournament
      hydrationSection = "live_fallback_upcoming"
    } else {
      source = snapshot.legacy_tournament
      hydrationSection = "legacy"
    }
  } else if (snapshot.upcoming_tournament) {
    source = snapshot.upcoming_tournament
    hydrationSection = "upcoming"
  } else if (snapshot.live_tournament?.active && !sameEventContext) {
    source = snapshot.live_tournament
    hydrationSection = "upcoming_fallback_live"
  } else {
    source = snapshot.legacy_tournament
    hydrationSection = "legacy"
  }

  return buildPredictionRunFromSection(source, {
    preferLivePlayerBoard: tab === "live",
    hydrationSection,
  })
}

export function buildPredictionRunFromSection(
  source: LiveTournamentSnapshot | null | undefined,
  options: HydrationOptions = {},
): PredictionRunResponse | null {
  if (!source) {
    return null
  }

  const eligibility = source.eligibility
  const completedReplay = Boolean(source.completed_replay)
  if (eligibility && eligibility.verified === false && !completedReplay) {
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
      model_variant: source.model_variant,
      ranking_source: source.ranking_source,
      composite_results: [],
      matchup_bets: [],
      value_bets: {},
      errors: [warning],
      warnings: [warning],
      hydration_section: options.hydrationSection,
    }
  }

  const rankings = source.live_rankings ?? source.rankings ?? []
  const liveActionableOnly =
    options.hydrationSection === "live" || options.hydrationSection === "live_fallback_upcoming"
  const matchupBets = hydrateSnapshotMatchups(source, { liveActionableOnly })
  const matchupBetsAllBooks = hydrateSnapshotMatchupsAllBooks(source)
  const valueBets = hydrateSnapshotValueBets(source)

  const livePlayerBoard =
    source.live_player_board && source.live_player_board.length > 0
      ? source.live_player_board
      : null
  const useLivePlayerBoard = options.preferLivePlayerBoard !== false && livePlayerBoard != null

  const rankingRows = useLivePlayerBoard
    ? livePlayerBoard.map((row, index) => ({
      player_key: row.player_key ?? normalizeNameForUi(row.player),
      player_display: row.player ?? "Unknown player",
      rank: Number(row.model?.current_rank ?? index + 1),
      composite: Number(row.model?.composite ?? 0),
      course_fit: 0,
      form: 0,
      momentum: Number(row.model?.momentum ?? 0),
      momentum_direction: row.model?.momentum_direction ?? undefined,
      momentum_trend: row.model?.momentum_trend != null ? Number(row.model.momentum_trend) : undefined,
      start_rank: row.model?.start_rank ?? null,
      current_rank: row.model?.current_rank ?? null,
      rank_delta: row.model?.rank_delta ?? null,
      start_composite: row.model?.start_composite ?? null,
      pre_tournament_composite: row.model?.pre_tournament_composite ?? null,
      leaderboard_rank: row.scoring?.position_rank ?? null,
      leaderboard_position: row.scoring?.position_label ?? null,
      start_leaderboard_rank: row.scoring?.start_position_rank ?? null,
      start_leaderboard_position: row.scoring?.start_position ?? null,
      leaderboard_delta: row.scoring?.position_delta ?? null,
      leaderboard_baseline_source: row.scoring?.baseline_source ?? null,
      total_to_par: row.scoring?.total_to_par ?? null,
    }))
    : rankings.map((row) => ({
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
      current_rank: row.current_rank != null ? Number(row.current_rank) : undefined,
      start_rank: row.start_rank != null ? Number(row.start_rank) : undefined,
      rank_delta: row.rank_delta != null ? Number(row.rank_delta) : undefined,
      start_composite: row.start_composite != null ? Number(row.start_composite) : undefined,
      pre_tournament_composite: row.pre_tournament_composite != null ? Number(row.pre_tournament_composite) : undefined,
      leaderboard_rank: row.leaderboard_rank != null ? Number(row.leaderboard_rank) : undefined,
      leaderboard_position: row.leaderboard_position ?? undefined,
      start_leaderboard_rank: row.start_leaderboard_rank != null ? Number(row.start_leaderboard_rank) : undefined,
      start_leaderboard_position: row.start_leaderboard_position ?? undefined,
      leaderboard_delta: row.leaderboard_delta != null ? Number(row.leaderboard_delta) : undefined,
      leaderboard_baseline_source: row.leaderboard_baseline_source ?? undefined,
      total_to_par: row.total_to_par != null ? Number(row.total_to_par) : undefined,
    }))

  const hydrationWarnings: string[] = []
  if (options.hydrationSection === "upcoming_fallback_live") {
    hydrationWarnings.push(
      "Upcoming board is using live snapshot data — upcoming section was unavailable.",
    )
  } else if (options.hydrationSection === "live_fallback_upcoming") {
    hydrationWarnings.push(
      "Live board is using upcoming snapshot data — live section was unavailable.",
    )
  }

  return {
    status: "hydrated",
    event_name: source.event_name ?? "Event",
    course_name: source.course_name ?? "",
    field_size: source.field_size ?? rankings.length,
    tournament_id: source.tournament_id,
    course_num: source.course_num,
    model_variant: source.model_variant,
    ranking_source: source.ranking_source,
    hydration_section: options.hydrationSection,
    composite_results: rankingRows,
    matchup_bets: matchupBets,
    matchup_bets_all_books: matchupBetsAllBooks,
    value_bets: valueBets,
    warnings: [
      "Hydrated from snapshot history. Manual runs are still required for card export and full provenance details.",
      ...(source.ranking_fallback_reason ? [source.ranking_fallback_reason] : []),
      ...(source.live_stats_warning ? [String(source.live_stats_warning)] : []),
      ...hydrationWarnings,
    ],
    live_model_mode: source.live_model_mode,
    live_stats_fresh: source.live_stats_fresh,
  }
}
