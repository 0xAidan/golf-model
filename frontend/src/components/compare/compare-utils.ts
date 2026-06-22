import type {
  CompareEventMode,
  CompareFieldPlayer,
  ComponentDeltaRow,
  ComponentDriverSummary,
  CompareKpiSummary,
  GradedPickDiffRow,
  MatchupBucket,
  MatchupDiffRow,
  MatchupOverlap,
  RankDeltaRow,
  RankScatterPoint,
  SeasonEventCompareRow,
} from "@/components/compare/compare-types"
import type { FieldBoardPlayer, GradingSeasonEvent, LiveRankingRow, LiveTournamentSnapshot, MatchupBet, TrackRecordPick } from "@/lib/types"

export const DEFAULT_RANK_DISAGREEMENT_THRESHOLD = 3

export const matchupKey = (bet: Pick<MatchupBet, "pick_key" | "opponent_key">) =>
  `${(bet.pick_key || "").toLowerCase()}|${(bet.opponent_key || "").toLowerCase()}`

export const buildRankIndex = (rows: LiveRankingRow[] | undefined) => {
  const index = new Map<string, LiveRankingRow>()
  for (const row of rows ?? []) {
    const key = (row.player_key || "").toLowerCase()
    if (key) index.set(key, row)
  }
  return index
}

export const resolveSnapshotRankings = (
  section: LiveTournamentSnapshot | undefined | null,
): LiveRankingRow[] => {
  if (!section) return []
  return (
    section.rankings ??
    section.frozen_pre_teeoff_rankings ??
    section.live_rankings ??
    section.pre_tournament_rankings ??
    []
  )
}

const positiveEvPlayers = (bets: MatchupBet[] | undefined) => {
  const players = new Set<string>()
  for (const bet of bets ?? []) {
    if ((bet.ev ?? 0) > 0) {
      const key = (bet.pick_key || "").toLowerCase()
      if (key) players.add(key)
    }
  }
  return players
}

export const buildFieldBoardPlayers = (
  championSection: LiveTournamentSnapshot | undefined,
  challengerSection: LiveTournamentSnapshot | null | undefined,
): CompareFieldPlayer[] => {
  const champRanks = buildRankIndex(resolveSnapshotRankings(championSection))
  const labRanks = buildRankIndex(resolveSnapshotRankings(challengerSection))
  const champEv = positiveEvPlayers(championSection?.matchup_bets)
  const matchupCount: Record<string, number> = {}
  for (const bet of championSection?.matchup_bets ?? []) {
    for (const who of [(bet.pick_key || "").toLowerCase(), (bet.opponent_key || "").toLowerCase()]) {
      if (who) matchupCount[who] = (matchupCount[who] ?? 0) + 1
    }
  }

  const players: CompareFieldPlayer[] = []
  for (const [key, row] of champRanks) {
    const labRow = labRanks.get(key)
    const championRank = row.rank ?? null
    const challengerRank = labRow?.rank ?? null
    const rankDelta =
      championRank !== null && challengerRank !== null ? championRank - challengerRank : null
    players.push({
      player_key: row.player_key || key,
      player: row.player,
      champion_rank: championRank,
      challenger_rank: challengerRank,
      rank_delta: rankDelta,
      composite: row.composite ?? null,
      course_fit: row.course_fit ?? null,
      form: row.form ?? null,
      momentum: row.momentum ?? null,
      momentum_direction: row.momentum_direction,
      momentum_trend: row.momentum_trend,
      course_confidence: row.course_confidence,
      finish_state: row.finish_state,
      matchup_count: matchupCount[key] ?? 0,
      in_positive_ev: champEv.has(key),
      has_sg: false,
      champion_composite: row.composite ?? null,
      challenger_composite: labRow?.composite ?? null,
      champion_form: row.form ?? null,
      challenger_form: labRow?.form ?? null,
      champion_course_fit: row.course_fit ?? null,
      challenger_course_fit: labRow?.course_fit ?? null,
      champion_momentum: row.momentum ?? null,
      challenger_momentum: labRow?.momentum ?? null,
    })
  }
  players.sort((a, b) => (a.champion_rank ?? 999) - (b.champion_rank ?? 999))
  return players
}

const gradedPickKey = (pick: TrackRecordPick) =>
  [
    (pick.bet_type || "matchup").toLowerCase(),
    (pick.player_key || pick.player_display || "").toLowerCase(),
    (pick.opponent_key || pick.opponent_display || "").toLowerCase(),
    (pick.market_book || "").toLowerCase(),
  ].join("|")

export const computeGradedPickDiffRows = (
  championPicks: TrackRecordPick[] | undefined,
  challengerPicks: TrackRecordPick[] | undefined,
): GradedPickDiffRow[] => {
  const champ = new Map<string, TrackRecordPick>()
  for (const pick of championPicks ?? []) champ.set(gradedPickKey(pick), pick)
  const chall = new Map<string, TrackRecordPick>()
  for (const pick of challengerPicks ?? []) chall.set(gradedPickKey(pick), pick)
  const keys = new Set<string>([...champ.keys(), ...chall.keys()])
  const rows: GradedPickDiffRow[] = []
  for (const key of keys) {
    const championPick = champ.get(key)
    const challengerPick = chall.get(key)
    const source = championPick ?? challengerPick
    if (!source) continue
    const bucket: MatchupBucket =
      championPick && challengerPick ? "both" : championPick ? "champion_only" : "challenger_only"
    rows.push({
      key,
      pick: source.player_display,
      opponent: source.opponent_display || "—",
      betType: source.bet_type || "—",
      book: source.market_book || "—",
      championEv: numOrNull(championPick?.ev),
      challengerEv: numOrNull(challengerPick?.ev),
      championProfit: numOrNull(championPick?.profit),
      challengerProfit: numOrNull(challengerPick?.profit),
      championHit: championPick?.hit == null ? null : championPick.hit === 1,
      challengerHit: challengerPick?.hit == null ? null : challengerPick.hit === 1,
      bucket,
    })
  }
  rows.sort(
    (a, b) =>
      Math.abs((b.championProfit ?? 0) - (b.challengerProfit ?? 0)) -
      Math.abs((a.championProfit ?? 0) - (a.challengerProfit ?? 0)),
  )
  return rows
}

export const buildSeasonEventCompareRows = (
  events: GradingSeasonEvent[] | undefined,
): SeasonEventCompareRow[] =>
  (events ?? [])
    .filter((event) => event.lanes?.dashboard || event.lanes?.lab)
    .map((event) => {
      const dash = event.lanes?.dashboard?.record
      const lab = event.lanes?.lab?.record
      return {
        eventId: String(event.event_id ?? event.tournament_id ?? event.name),
        name: event.name,
        eventDate: event.event_date,
        championPnl: dash?.profit ?? event.lanes?.dashboard?.total_profit ?? null,
        challengerPnl: lab?.profit ?? event.lanes?.lab?.total_profit ?? null,
        profitDelta: event.comparison?.profit_delta ?? null,
        championHitRate:
          dash?.hit_rate == null ? null : dash.hit_rate <= 1 ? dash.hit_rate * 100 : dash.hit_rate,
        challengerHitRate:
          lab?.hit_rate == null ? null : lab.hit_rate <= 1 ? lab.hit_rate * 100 : lab.hit_rate,
        overlapMatchups: event.comparison?.overlap_matchups ?? null,
        picksOnlyChampion: event.comparison?.picks_only_dashboard ?? null,
        picksOnlyChallenger: event.comparison?.picks_only_lab ?? null,
        status: event.status,
      }
    })
    .sort((a, b) => String(b.eventDate ?? "").localeCompare(String(a.eventDate ?? "")))

const numOrNull = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null

const deltaOrNull = (a: number | null, b: number | null): number | null =>
  a !== null && b !== null ? a - b : null

export const median = (values: number[]): number | null => {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2
  }
  return sorted[mid]
}

export const computeRankDeltas = (
  championRankings: LiveRankingRow[] | undefined,
  challengerRankings: LiveRankingRow[] | undefined,
  limit?: number,
): RankDeltaRow[] => {
  const champIndex = buildRankIndex(championRankings)
  const challIndex = buildRankIndex(challengerRankings)
  const keys = new Set<string>([...champIndex.keys(), ...challIndex.keys()])
  const rows: RankDeltaRow[] = []
  for (const key of keys) {
    const champ = champIndex.get(key)
    const chall = challIndex.get(key)
    const championRank = champ?.rank ?? null
    const challengerRank = chall?.rank ?? null
    const delta =
      championRank !== null && challengerRank !== null ? championRank - challengerRank : null
    rows.push({
      playerKey: key,
      player: champ?.player || chall?.player || key,
      championRank,
      challengerRank,
      delta,
    })
  }
  rows.sort((a, b) => {
    const da = a.delta === null ? -1 : Math.abs(a.delta)
    const db = b.delta === null ? -1 : Math.abs(b.delta)
    return db - da
  })
  return limit === undefined ? rows : rows.slice(0, limit)
}

export const computeRankScatterPoints = (players: FieldBoardPlayer[]): RankScatterPoint[] =>
  players
    .filter(
      (p): p is FieldBoardPlayer & { champion_rank: number; challenger_rank: number } =>
        typeof p.champion_rank === "number" && typeof p.challenger_rank === "number",
    )
    .map((p) => ({
      playerKey: p.player_key,
      player: p.player,
      championRank: p.champion_rank,
      challengerRank: p.challenger_rank,
      delta: p.champion_rank - p.challenger_rank,
    }))

export const computeComponentDeltaRows = (
  championRankings: LiveRankingRow[] | undefined,
  challengerRankings: LiveRankingRow[] | undefined,
): ComponentDeltaRow[] => {
  const champIndex = buildRankIndex(championRankings)
  const challIndex = buildRankIndex(challengerRankings)
  const keys = new Set<string>([...champIndex.keys(), ...challIndex.keys()])
  const rows: ComponentDeltaRow[] = []
  for (const key of keys) {
    const champ = champIndex.get(key)
    const chall = challIndex.get(key)
    if (!champ || !chall) continue
    const championRank = numOrNull(champ.rank)
    const challengerRank = numOrNull(chall.rank)
    rows.push({
      playerKey: key,
      player: champ.player || chall.player || key,
      rankDelta:
        championRank !== null && challengerRank !== null ? championRank - challengerRank : null,
      compositeDelta: deltaOrNull(numOrNull(champ.composite), numOrNull(chall.composite)),
      formDelta: deltaOrNull(numOrNull(champ.form), numOrNull(chall.form)),
      courseFitDelta: deltaOrNull(numOrNull(champ.course_fit), numOrNull(chall.course_fit)),
      momentumDelta: deltaOrNull(numOrNull(champ.momentum), numOrNull(chall.momentum)),
    })
  }
  return rows
}

export const computeComponentDriverSummary = (
  rows: ComponentDeltaRow[],
  threshold = DEFAULT_RANK_DISAGREEMENT_THRESHOLD,
): ComponentDriverSummary => {
  const filtered = rows.filter(
    (r) => r.rankDelta !== null && Math.abs(r.rankDelta) >= threshold,
  )
  const meanAbs = (values: Array<number | null>) => {
    const nums = values.filter((v): v is number => v !== null).map((v) => Math.abs(v))
    if (nums.length === 0) return 0
    return nums.reduce((sum, v) => sum + v, 0) / nums.length
  }
  return {
    composite: meanAbs(filtered.map((r) => r.compositeDelta)),
    form: meanAbs(filtered.map((r) => r.formDelta)),
    courseFit: meanAbs(filtered.map((r) => r.courseFitDelta)),
    momentum: meanAbs(filtered.map((r) => r.momentumDelta)),
    sampleSize: filtered.length,
  }
}

export const topComponentDeltaRows = (
  rows: ComponentDeltaRow[],
  limit = 10,
): ComponentDeltaRow[] =>
  [...rows]
    .filter((r) => r.compositeDelta !== null)
    .sort((a, b) => Math.abs(b.compositeDelta ?? 0) - Math.abs(a.compositeDelta ?? 0))
    .slice(0, limit)

export const computeMatchupOverlap = (
  championBets: MatchupBet[] | undefined,
  challengerBets: MatchupBet[] | undefined,
): MatchupOverlap => {
  const champ = new Map<string, MatchupBet>()
  for (const bet of championBets ?? []) champ.set(matchupKey(bet), bet)
  const chall = new Map<string, MatchupBet>()
  for (const bet of challengerBets ?? []) chall.set(matchupKey(bet), bet)
  const both: MatchupBet[] = []
  const championOnly: MatchupBet[] = []
  const challengerOnly: MatchupBet[] = []
  for (const [key, bet] of champ) {
    if (chall.has(key)) both.push(bet)
    else championOnly.push(bet)
  }
  for (const [key, bet] of chall) {
    if (!champ.has(key)) challengerOnly.push(bet)
  }
  return { both, championOnly, challengerOnly }
}

const betEv = (bet: MatchupBet | undefined): number | null => numOrNull(bet?.ev)
const betProb = (bet: MatchupBet | undefined): number | null => numOrNull(bet?.model_win_prob)

export const computeMatchupDiffRows = (
  championBets: MatchupBet[] | undefined,
  challengerBets: MatchupBet[] | undefined,
): MatchupDiffRow[] => {
  const champ = new Map<string, MatchupBet>()
  for (const bet of championBets ?? []) champ.set(matchupKey(bet), bet)
  const chall = new Map<string, MatchupBet>()
  for (const bet of challengerBets ?? []) chall.set(matchupKey(bet), bet)
  const keys = new Set<string>([...champ.keys(), ...chall.keys()])
  const rows: MatchupDiffRow[] = []
  for (const key of keys) {
    const championBet = champ.get(key)
    const challengerBet = chall.get(key)
    const source = championBet ?? challengerBet
    if (!source) continue
    const bucket: MatchupBucket =
      championBet && challengerBet ? "both" : championBet ? "champion_only" : "challenger_only"
    const championEv = betEv(championBet)
    const challengerEv = betEv(challengerBet)
    rows.push({
      key,
      pick: source.pick,
      pickKey: source.pick_key,
      opponent: source.opponent,
      opponentKey: source.opponent_key,
      book: source.book ?? "—",
      championEv,
      challengerEv,
      evDelta: championEv !== null && challengerEv !== null ? challengerEv - championEv : null,
      championProb: betProb(championBet),
      challengerProb: betProb(challengerBet),
      bucket,
    })
  }
  rows.sort((a, b) => Math.abs(b.evDelta ?? 0) - Math.abs(a.evDelta ?? 0))
  return rows
}

export const filterMatchupDiffRows = (
  rows: MatchupDiffRow[],
  bucket: MatchupBucket,
): MatchupDiffRow[] => rows.filter((r) => r.bucket === bucket)

export const computeKpiSummary = (input: {
  eventName: string
  eventMode?: CompareEventMode
  modeLabel?: string
  usingLive: boolean
  players: FieldBoardPlayer[]
  overlap: MatchupOverlap
  championGradedPnl?: number | null
  challengerGradedPnl?: number | null
  gradedProfitDelta?: number | null
}): CompareKpiSummary => {
  const absDeltas = input.players
    .map((p) => p.rank_delta)
    .filter((d): d is number => d !== null)
    .map((d) => Math.abs(d))
  const bothRankedCount = input.players.filter(
    (p) => p.champion_rank !== null && p.challenger_rank !== null,
  ).length
  let maxDisagreement: CompareKpiSummary["maxDisagreement"] = null
  for (const p of input.players) {
    if (p.rank_delta === null) continue
    const abs = Math.abs(p.rank_delta)
    if (!maxDisagreement || abs > Math.abs(maxDisagreement.delta)) {
      maxDisagreement = { player: p.player, delta: p.rank_delta }
    }
  }
  return {
    eventName: input.eventName,
    eventMode: input.eventMode ?? "current",
    modeLabel: input.modeLabel ?? (input.usingLive ? "Live" : "Upcoming"),
    usingLive: input.usingLive,
    fieldSize: input.players.length,
    bothRankedCount,
    meanAbsRankDelta:
      absDeltas.length > 0 ? absDeltas.reduce((s, v) => s + v, 0) / absDeltas.length : null,
    medianAbsRankDelta: median(absDeltas),
    overlapBoth: input.overlap.both.length,
    overlapChampionOnly: input.overlap.championOnly.length,
    overlapChallengerOnly: input.overlap.challengerOnly.length,
    maxDisagreement,
    championGradedPnl: input.championGradedPnl,
    challengerGradedPnl: input.challengerGradedPnl,
    gradedProfitDelta: input.gradedProfitDelta,
  }
}
