import { useCallback, useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { CompositePlayer } from "@/lib/types"

import type { FieldExplorerFilter, FieldExplorerSort } from "./player-workspace-types"

export type FieldExplorerRow = {
  player_key: string
  player_display: string
  inField: boolean
  model?: CompositePlayer
}

const sortRows = (rows: FieldExplorerRow[], sort: FieldExplorerSort): FieldExplorerRow[] => {
  const copy = [...rows]
  copy.sort((a, b) => {
    switch (sort) {
      case "name":
        return a.player_display.localeCompare(b.player_display)
      case "composite":
        return (b.model?.composite ?? -Infinity) - (a.model?.composite ?? -Infinity)
      case "form":
        return (b.model?.form ?? -Infinity) - (a.model?.form ?? -Infinity)
      case "trajectory":
        return (b.model?.momentum_trend ?? -Infinity) - (a.model?.momentum_trend ?? -Infinity)
      case "rank":
      default:
        return (a.model?.rank ?? 9999) - (b.model?.rank ?? 9999)
    }
  })
  return copy
}

export const useFieldExplorer = ({
  players,
  selectedKey,
  onSelect,
}: {
  players: CompositePlayer[]
  selectedKey: string | null
  onSelect: (key: string, display: string) => void
}) => {
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<FieldExplorerSort>("rank")
  const [filter, setFilter] = useState<FieldExplorerFilter>("field")

  const searchQuery = useQuery({
    queryKey: ["player-search", query],
    queryFn: () => api.searchPlayers(query),
    enabled: query.length >= 2,
    staleTime: 30_000,
  })

  const showSearch = query.length >= 2
  const searchResults = useMemo(() => searchQuery.data?.players ?? [], [searchQuery.data])

  const filteredActive = useMemo(() => {
    if (!query) return players
    const q = query.toLowerCase()
    return players.filter(
      (p) => p.player_display.toLowerCase().includes(q) || p.player_key.includes(q),
    )
  }, [players, query])

  const activeByKey = useMemo(
    () => new Map(players.map((p) => [p.player_key, p])),
    [players],
  )

  const displayList = useMemo((): FieldExplorerRow[] => {
    if (!showSearch) {
      return filteredActive.map((p) => ({
        player_key: p.player_key,
        player_display: p.player_display,
        inField: true,
        model: p,
      }))
    }
    const activeKeys = new Set(filteredActive.map((p) => p.player_key))
    const dbOnly = searchResults.filter((r) => !activeKeys.has(r.player_key))
    return [
      ...filteredActive.map((p) => ({
        player_key: p.player_key,
        player_display: p.player_display,
        inField: true,
        model: p,
      })),
      ...dbOnly.map((r) => ({
        player_key: r.player_key,
        player_display: r.player_display,
        inField: false,
        model: activeByKey.get(r.player_key),
      })),
    ]
  }, [activeByKey, filteredActive, searchResults, showSearch])

  const filteredList = useMemo(() => {
    const base = filter === "field" ? displayList.filter((r) => r.inField) : displayList
    return sortRows(base, sort)
  }, [displayList, filter, sort])

  const handleKeyboardNav = useCallback(
    (direction: 1 | -1) => {
      if (!filteredList.length) return
      const currentIndex = filteredList.findIndex((r) => r.player_key === selectedKey)
      const nextIndex =
        currentIndex < 0
          ? direction > 0
            ? 0
            : filteredList.length - 1
          : Math.min(filteredList.length - 1, Math.max(0, currentIndex + direction))
      const next = filteredList[nextIndex]
      if (next) onSelect(next.player_key, next.player_display)
    },
    [filteredList, onSelect, selectedKey],
  )

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable
      ) {
        return
      }
      if (e.key === "ArrowDown") {
        e.preventDefault()
        handleKeyboardNav(1)
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        handleKeyboardNav(-1)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [handleKeyboardNav])

  return {
    query,
    setQuery,
    sort,
    setSort,
    filter,
    setFilter,
    displayList: filteredList,
    isSearching: showSearch && searchQuery.isFetching,
  }
}
