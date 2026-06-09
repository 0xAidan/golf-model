import type { FlattenedSecondaryBet, MatchupBet } from "@/lib/types"

import type { LinkedPicksBundle } from "./player-workspace-types"

export const filterLinkedPicks = (
  playerKey: string,
  matchups: MatchupBet[],
  secondaryBets: FlattenedSecondaryBet[],
): LinkedPicksBundle => {
  if (!playerKey) {
    return { matchups: [], secondary: [], totalCount: 0 }
  }

  const linkedMatchups = matchups.filter(
    (m) => m.pick_key === playerKey || m.opponent_key === playerKey,
  )
  const linkedSecondary = secondaryBets.filter((b) => b.player_key === playerKey)

  return {
    matchups: linkedMatchups,
    secondary: linkedSecondary,
    totalCount: linkedMatchups.length + linkedSecondary.length,
  }
}
