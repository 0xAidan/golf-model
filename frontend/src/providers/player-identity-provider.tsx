import { createContext, useContext, useMemo, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type PlayerIdentity = {
  country?: string
  hasPhoto: boolean
}

type PlayerIdentityContextValue = {
  byKey: Record<string, PlayerIdentity>
  loaded: boolean
}

const PlayerIdentityContext = createContext<PlayerIdentityContextValue>({
  byKey: {},
  loaded: false,
})

export const PlayerIdentityProvider = ({ children }: { children: ReactNode }) => {
  const query = useQuery({
    queryKey: ["player-photo-index"],
    queryFn: api.getPlayerPhotoIndex,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const byKey = useMemo(() => {
    const players = query.data?.players ?? {}
    const mapped: Record<string, PlayerIdentity> = {}
    for (const [key, row] of Object.entries(players)) {
      mapped[key] = {
        country: row.country || undefined,
        hasPhoto: Boolean(row.has_photo),
      }
    }
    return mapped
  }, [query.data])

  const loaded = query.isFetched || query.isError
  const value = useMemo(() => ({ byKey, loaded }), [byKey, loaded])
  return <PlayerIdentityContext.Provider value={value}>{children}</PlayerIdentityContext.Provider>
}

export const usePlayerIdentity = (playerKey?: string | null): PlayerIdentity | null => {
  const ctx = useContext(PlayerIdentityContext)
  if (!playerKey) return null
  return ctx.byKey[playerKey] ?? null
}

export const usePlayerIdentityIndexLoaded = () => useContext(PlayerIdentityContext).loaded
