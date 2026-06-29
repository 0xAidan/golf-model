import type { MatchupBet, TrackRecordPick } from "@/lib/types"

const normalizeKey = (value: string | undefined | null): string =>
  String(value ?? "")
    .trim()
    .toLowerCase()

const normalizeMarketType = (value: string | undefined | null): string =>
  String(value ?? "tournament_matchups").trim().toLowerCase()

const buildMatchupMergeKey = (
  betType: string,
  playerKey: string,
  opponentKey: string,
  marketType?: string | null,
): string =>
  [
    normalizeKey(betType || "matchup"),
    normalizeMarketType(marketType),
    normalizeKey(playerKey),
    normalizeKey(opponentKey),
  ].join("|")

const matchupPickKeys = (pick: TrackRecordPick): string[] => {
  const marketType = pick.market_type
  const playerKeys = [pick.player_key, pick.player_display].filter(Boolean)
  const opponentKeys = [pick.opponent_key, pick.opponent_display].filter(Boolean)
  const keys = new Set<string>()
  for (const player of playerKeys) {
    for (const opponent of opponentKeys) {
      keys.add(buildMatchupMergeKey("matchup", String(player), String(opponent), marketType))
    }
  }
  return Array.from(keys)
}

const storedOutcomeFromPick = (pick: TrackRecordPick): "win" | "loss" | "push" | null => {
  if (pick.outcome === "win" || pick.outcome === "loss" || pick.outcome === "push") {
    return pick.outcome
  }
  if (Number(pick.hit ?? 0) === 1) return "win"
  if (Number(pick.profit ?? 0) === 0 && pick.hit === 0) return "push"
  if (pick.hit != null) return "loss"
  return null
}

export const applyGradedPicksToMatchups = (
  matchups: MatchupBet[],
  gradedPicks: TrackRecordPick[] | undefined | null,
): MatchupBet[] => {
  if (!gradedPicks?.length) return matchups

  const gradedByKey = new Map<string, TrackRecordPick>()
  for (const pick of gradedPicks) {
    if (String(pick.bet_type ?? "").trim().toLowerCase() !== "matchup") continue
    for (const key of matchupPickKeys(pick)) {
      gradedByKey.set(key, pick)
    }
  }

  return matchups.map((matchup) => {
    if (matchup.graded_result) return matchup
    const lookupKeys = [
      buildMatchupMergeKey(
        "matchup",
        matchup.pick_key ?? matchup.pick,
        matchup.opponent_key ?? matchup.opponent,
        matchup.market_type,
      ),
      buildMatchupMergeKey("matchup", matchup.pick, matchup.opponent, matchup.market_type),
    ]
    let graded: TrackRecordPick | undefined
    for (const key of lookupKeys) {
      graded = gradedByKey.get(key)
      if (graded) break
    }
    const stored = graded ? storedOutcomeFromPick(graded) : null
    if (!stored) return matchup
    return { ...matchup, graded_result: stored }
  })
}
