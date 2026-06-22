import type {
  ComponentDeltaRow,
  ComponentDriverSummary,
  CompareKpiSummary,
  MatchupBucket,
  MatchupDiffRow,
  MatchupOverlap,
  RankDeltaRow,
  RankScatterPoint,
} from "@/components/compare/compare-types"
import type { FieldBoardPlayer, LiveRankingRow, MatchupBet } from "@/lib/types"

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
  usingLive: boolean
  players: FieldBoardPlayer[]
  overlap: MatchupOverlap
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
  }
}
