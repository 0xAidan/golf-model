import { useEffect, useMemo } from "react"

import type { PredictionTab } from "@/hooks/use-prediction-tab"
import { buildCockpitSpotlight } from "@/lib/cockpit-spotlight"
import type { CompositePlayer, FlattenedSecondaryBet, LiveLeaderboardRow, MatchupBet } from "@/lib/types"

type UseCockpitSpotlightInput = {
  predictionTab: PredictionTab
  isLiveActive: boolean
  eventName: string
  selectedPlayerKey: string
  onPlayerSelect: (playerKey: string) => void
  players: CompositePlayer[]
  leaderboardRows: LiveLeaderboardRow[]
  topPlays: MatchupBet[]
  rawGeneratedMatchups: MatchupBet[]
  rawGeneratedSecondaryBets: FlattenedSecondaryBet[]
}

export function useCockpitSpotlight({
  predictionTab,
  isLiveActive,
  eventName,
  selectedPlayerKey,
  onPlayerSelect,
  players,
  leaderboardRows,
  topPlays,
  rawGeneratedMatchups,
  rawGeneratedSecondaryBets,
}: UseCockpitSpotlightInput) {
  const hasLiveContext = predictionTab !== "live" || isLiveActive

  const playerKeyByName = useMemo(() => {
    const entries = new Map<string, string>()

    players.forEach((player) => {
      entries.set(normalizeName(player.player_display), player.player_key)
    })

    leaderboardRows.forEach((row) => {
      if (row.player_key) {
        entries.set(normalizeName(row.player), row.player_key)
      }
    })

    rawGeneratedMatchups.forEach((matchup) => {
      if (matchup.pick_key) {
        entries.set(normalizeName(matchup.pick), matchup.pick_key)
      }
      if (matchup.opponent_key) {
        entries.set(normalizeName(matchup.opponent), matchup.opponent_key)
      }
    })

    rawGeneratedSecondaryBets.forEach((bet) => {
      if (bet.player_key) {
        entries.set(normalizeName(bet.player_display ?? bet.player), bet.player_key)
      }
    })

    return entries
  }, [leaderboardRows, players, rawGeneratedMatchups, rawGeneratedSecondaryBets])

  const spotlightCandidateKeys = useMemo(() => {
    if (!hasLiveContext) {
      return []
    }

    const keys = new Set<string>()

    players.forEach((player) => keys.add(player.player_key))
    leaderboardRows.forEach((row) => {
      if (row.player_key) {
        keys.add(row.player_key)
      }
    })
    topPlays.forEach((matchup) => {
      if (matchup.pick_key) {
        keys.add(matchup.pick_key)
      }
      if (matchup.opponent_key) {
        keys.add(matchup.opponent_key)
      }
    })
    rawGeneratedMatchups.forEach((matchup) => {
      if (matchup.pick_key) {
        keys.add(matchup.pick_key)
      }
      if (matchup.opponent_key) {
        keys.add(matchup.opponent_key)
      }
    })
    rawGeneratedSecondaryBets.forEach((bet) => {
      const resolvedKey = bet.player_key ?? playerKeyByName.get(normalizeName(bet.player_display ?? bet.player))
      if (resolvedKey) {
        keys.add(resolvedKey)
      }
    })

    return [...keys]
  }, [hasLiveContext, leaderboardRows, playerKeyByName, players, rawGeneratedMatchups, rawGeneratedSecondaryBets, topPlays])

  useEffect(() => {
    const nextKey = spotlightCandidateKeys[0]
    if (!nextKey) {
      return
    }
    if (selectedPlayerKey && spotlightCandidateKeys.includes(selectedPlayerKey)) {
      return
    }
    onPlayerSelect(nextKey)
  }, [onPlayerSelect, selectedPlayerKey, spotlightCandidateKeys])

  const selectedPlayer = useMemo(
    () => players.find((player) => player.player_key === selectedPlayerKey) ?? null,
    [players, selectedPlayerKey],
  )

  const spotlightMode: PredictionTab =
    predictionTab === "live" && !isLiveActive ? "upcoming" : predictionTab

  const spotlight = useMemo(
    () => {
      if (!hasLiveContext) {
        return null
      }

      return buildCockpitSpotlight({
        predictionTab: spotlightMode,
        eventName,
        selectedPlayerKey,
        players,
        leaderboardRows,
        topPlays,
        rawGeneratedMatchups,
        rawGeneratedSecondaryBets,
      })
    },
    [
      eventName,
      hasLiveContext,
      leaderboardRows,
      players,
      rawGeneratedMatchups,
      rawGeneratedSecondaryBets,
      selectedPlayerKey,
      spotlightMode,
      topPlays,
    ],
  )

  return {
    playerKeyByName,
    selectedPlayer,
    spotlight,
    spotlightCandidateKeys,
    spotlightMode,
  }
}

function normalizeName(value: string) {
  return value.toLowerCase().trim()
}
