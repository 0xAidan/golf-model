import type { FlattenedSecondaryBet, MatchupBet } from "@/lib/types"

const americanOddsRank = (odds: string | number | undefined | null): number => {
  if (odds == null) return -1_000_000
  const raw = String(odds).trim().replace("+", "")
  const parsed = Number.parseInt(raw, 10)
  return Number.isFinite(parsed) ? parsed : -1_000_000
}

const normalizeMarketType = (value: string | undefined | null): string => {
  const raw = String(value ?? "").trim().toLowerCase()
  if (!raw || raw === "matchup" || raw === "matchups") return "tournament_matchups"
  return raw
}

const matchupIdentityKey = (matchup: MatchupBet): string =>
  [
    normalizeMarketType(matchup.market_type),
    String(matchup.pick_key ?? matchup.pick ?? "").trim().toLowerCase(),
    String(matchup.opponent_key ?? matchup.opponent ?? "").trim().toLowerCase(),
  ].join("|")

const outrightIdentityKey = (bet: FlattenedSecondaryBet): string =>
  [
    String(bet.market ?? "").trim().toLowerCase(),
    String(bet.player_key ?? bet.player_display ?? bet.player ?? "").trim().toLowerCase(),
  ].join("|")

export const dedupeReplayMatchups = (matchups: MatchupBet[]): MatchupBet[] => {
  const deduped: MatchupBet[] = []
  const indexes = new Map<string, number>()

  for (const matchup of matchups) {
    if (Number(matchup.ev ?? 0) <= 0) continue
    const key = matchupIdentityKey(matchup)
    const existingIndex = indexes.get(key)
    if (existingIndex === undefined) {
      indexes.set(key, deduped.length)
      deduped.push(matchup)
      continue
    }
    if (americanOddsRank(matchup.odds) > americanOddsRank(deduped[existingIndex]?.odds)) {
      deduped[existingIndex] = matchup
    }
  }

  return deduped
}

export const dedupeReplaySecondaryBets = (bets: FlattenedSecondaryBet[]): FlattenedSecondaryBet[] => {
  const deduped: FlattenedSecondaryBet[] = []
  const indexes = new Map<string, number>()

  for (const bet of bets) {
    if (Number(bet.ev ?? 0) <= 0) continue
    const key = outrightIdentityKey(bet)
    const existingIndex = indexes.get(key)
    if (existingIndex === undefined) {
      indexes.set(key, deduped.length)
      deduped.push(bet)
      continue
    }
    if (americanOddsRank(bet.odds) > americanOddsRank(deduped[existingIndex]?.odds)) {
      deduped[existingIndex] = bet
    }
  }

  return deduped
}
