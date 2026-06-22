import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"

import type { CompareEventMode, CompareEventOption, CompareFieldPlayer, CompareTrackSections } from "@/components/compare/compare-types"
import { buildFieldBoardPlayers, resolveSnapshotRankings } from "@/components/compare/compare-utils"
import { api } from "@/lib/api"
import { POLLING } from "@/lib/query-polling"
import type { GradingSeasonEvent, LiveTournamentSnapshot } from "@/lib/types"

const CURRENT_EVENT_ID = "current"

export function useCompareEventOptions() {
  const pastEventsQuery = useQuery({
    queryKey: ["compare-past-events"],
    queryFn: api.getLiveRefreshPastEvents,
    staleTime: 5 * 60_000,
  })

  const gradingQuery = useQuery({
    queryKey: ["compare-grading-season"],
    queryFn: () => api.getGradingSeason({ lane: "all", includePicks: true, limit: 200 }),
    staleTime: 60_000,
  })

  const options = useMemo<CompareEventOption[]>(() => {
    const list: CompareEventOption[] = [
      {
        eventId: CURRENT_EVENT_ID,
        label: "Current event",
        mode: "current",
      },
    ]
    const seen = new Set<string>()
    const gradingById = new Map<string, GradingSeasonEvent>()
    for (const event of gradingQuery.data?.events ?? []) {
      const id = String(event.event_id ?? "").trim()
      if (id) gradingById.set(id, event)
    }

    for (const event of pastEventsQuery.data?.events ?? []) {
      const id = String(event.event_id || "").trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      const graded = gradingById.get(id)
      list.push({
        eventId: id,
        label: event.event_name || graded?.name || id,
        mode: "past",
        hasSnapshots: (event.snapshot_count ?? 0) > 0,
        hasGrading: Boolean(graded?.lanes?.dashboard || graded?.lanes?.lab),
      })
    }

    for (const event of gradingQuery.data?.events ?? []) {
      const id = String(event.event_id ?? "").trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      list.push({
        eventId: id,
        label: event.name,
        mode: "past",
        hasSnapshots: false,
        hasGrading: true,
      })
    }

    return list
  }, [gradingQuery.data?.events, pastEventsQuery.data?.events])

  return {
    options,
    gradingEvents: gradingQuery.data?.events ?? [],
    seasonSummary: gradingQuery.data?.summary,
    isLoading: pastEventsQuery.isLoading || gradingQuery.isLoading,
  }
}

export function useCompareEventData({
  selectedEventId,
  liveTracks,
}: {
  selectedEventId: string
  liveTracks: CompareTrackSections
}) {
  const isCurrent = selectedEventId === CURRENT_EVENT_ID
  const section = liveTracks.usingLive ? "live" : "upcoming"

  const fieldBoardQuery = useQuery({
    queryKey: ["field-board", section],
    queryFn: () => api.getFieldBoard(section),
    enabled: isCurrent,
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const championPastQuery = useQuery({
    queryKey: ["compare-past-snapshot", selectedEventId, "dashboard"],
    queryFn: () => api.getLiveRefreshPastSnapshot(selectedEventId, "completed", { source: "dashboard" }),
    enabled: !isCurrent,
    staleTime: 5 * 60_000,
  })

  const challengerPastQuery = useQuery({
    queryKey: ["compare-past-snapshot", selectedEventId, "lab"],
    queryFn: () => api.getLiveRefreshPastSnapshot(selectedEventId, "completed", { source: "lab" }),
    enabled: !isCurrent,
    staleTime: 5 * 60_000,
  })

  const gradingQuery = useQuery({
    queryKey: ["compare-grading-season"],
    queryFn: () => api.getGradingSeason({ lane: "all", includePicks: true, limit: 200 }),
    staleTime: 60_000,
  })

  const gradingEvent = useMemo(
    () =>
      !isCurrent
        ? (gradingQuery.data?.events ?? []).find(
            (event) => String(event.event_id ?? "") === selectedEventId,
          )
        : undefined,
    [gradingQuery.data?.events, isCurrent, selectedEventId],
  )

  const championSection: LiveTournamentSnapshot | undefined = isCurrent
    ? liveTracks.champion
    : championPastQuery.data?.snapshot ?? undefined

  const challengerSection: LiveTournamentSnapshot | null | undefined = isCurrent
    ? liveTracks.challenger
    : challengerPastQuery.data?.snapshot ?? null

  const players = useMemo<CompareFieldPlayer[]>(() => {
    if (isCurrent) {
      const rows = fieldBoardQuery.data?.players ?? []
      return rows.map((row) => ({ ...row }))
    }
    return buildFieldBoardPlayers(championSection, challengerSection)
  }, [championSection, challengerSection, fieldBoardQuery.data?.players, isCurrent])

  const eventMode: CompareEventMode = isCurrent ? "current" : "past"
  const eventName =
    championSection?.event_name ||
    challengerSection?.event_name ||
    gradingEvent?.name ||
    fieldBoardQuery.data?.event_name ||
    "Event"

  const modeLabel = isCurrent
    ? liveTracks.usingLive
      ? "Live"
      : "Upcoming"
    : "Completed"

  const tracks: CompareTrackSections = {
    champion: championSection,
    challenger: challengerSection,
    usingLive: isCurrent ? liveTracks.usingLive : false,
    eventMode,
  }

  const isLoading = isCurrent
    ? fieldBoardQuery.isLoading
    : championPastQuery.isLoading || challengerPastQuery.isLoading

  const labAvailable = isCurrent
    ? (fieldBoardQuery.data?.lab_available ?? Boolean(challengerSection))
    : Boolean(resolveSnapshotRankings(challengerSection).length)

  const hasRankings = players.length > 0 || resolveSnapshotRankings(championSection).length > 0

  return {
    tracks,
    players,
    gradingEvent,
    eventName,
    eventMode,
    modeLabel,
    isLoading,
    labAvailable,
    hasRankings,
    isCurrent,
  }
}

export { CURRENT_EVENT_ID }
