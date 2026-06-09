import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { CompositePlayer, PlayerProfile } from "@/lib/types"

import { computePlayerFieldPercentiles } from "./field-percentiles"
import { filterLinkedPicks } from "./linked-picks"
import type { PlayerProfileLoadState, PlayerWorkspaceData } from "./player-workspace-types"

const resolveProfileState = ({
  enabled,
  isError,
  isPending,
  isFetching,
  data,
  playerKey,
}: {
  enabled: boolean
  isError: boolean
  isPending: boolean
  isFetching: boolean
  data: PlayerProfile | undefined
  playerKey: string
}): PlayerProfileLoadState => {
  if (!enabled) return "unavailable"
  if (isError) return "error"
  const matches = data?.player_key === playerKey
  if (isPending || (!matches && (isFetching || isPending))) return "loading"
  if (matches && data) return "ready"
  return "unavailable"
}

export const usePlayerWorkspace = ({
  playerKey,
  players,
  tournamentId,
  courseNum,
  richProfilesEnabled,
  filteredMatchups,
  secondaryBets,
}: {
  playerKey: string
  players: CompositePlayer[]
  tournamentId?: number | null
  courseNum?: number | null
  richProfilesEnabled: boolean
  filteredMatchups: Parameters<typeof filterLinkedPicks>[1]
  secondaryBets: Parameters<typeof filterLinkedPicks>[2]
}): PlayerWorkspaceData => {
  const hasTournament = tournamentId != null && tournamentId !== undefined

  const standaloneQuery = useQuery({
    queryKey: ["standalone-profile", playerKey],
    queryFn: () => api.getPlayerStandaloneProfile(playerKey),
    enabled: Boolean(playerKey),
    staleTime: 5 * 60_000,
    gcTime: 15 * 60_000,
    retry: 1,
    retryDelay: 1000,
  })

  const tournamentQuery = useQuery({
    queryKey: ["player-profile", "players-page", playerKey, tournamentId, courseNum],
    queryFn: () => {
      if (tournamentId == null) throw new Error("Missing tournament context")
      return api.getPlayerProfile(playerKey, tournamentId, courseNum ?? undefined)
    },
    enabled: Boolean(playerKey && richProfilesEnabled && hasTournament),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  })

  const modelPlayer = useMemo(
    () => players.find((p) => p.player_key === playerKey),
    [players, playerKey],
  )

  const linkedPicks = useMemo(
    () => filterLinkedPicks(playerKey, filteredMatchups, secondaryBets),
    [playerKey, filteredMatchups, secondaryBets],
  )

  const fieldPercentiles = useMemo(
    () => computePlayerFieldPercentiles(modelPlayer, players),
    [modelPlayer, players],
  )

  const standaloneState: PlayerProfileLoadState = standaloneQuery.isLoading
    ? "loading"
    : standaloneQuery.isError
      ? "error"
      : standaloneQuery.data
        ? "ready"
        : "unavailable"

  const tournamentState = resolveProfileState({
    enabled: Boolean(playerKey && richProfilesEnabled && hasTournament),
    isError: tournamentQuery.isError,
    isPending: tournamentQuery.isPending,
    isFetching: tournamentQuery.isFetching,
    data: tournamentQuery.data,
    playerKey,
  })

  return {
    standalone: standaloneQuery.data,
    standaloneState,
    standaloneError:
      standaloneQuery.error instanceof Error ? standaloneQuery.error.message : undefined,
    tournament: tournamentQuery.data,
    tournamentState,
    tournamentError:
      tournamentQuery.error instanceof Error ? tournamentQuery.error.message : undefined,
    modelPlayer,
    linkedPicks,
    fieldPercentiles,
    refetchStandalone: () => void standaloneQuery.refetch(),
    refetchTournament: () => void tournamentQuery.refetch(),
  }
}
