import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import type { PredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import { applyGradedPicksToMatchups } from "@/lib/apply-graded-picks"
import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
  getRawGeneratedMatchups,
  getRawGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import {
  buildPredictionRunFromSection,
  collectAvailableBooks,
  flattenSecondaryBets,
  NON_BOOK_SOURCES,
  normalizeSportsbook,
} from "@/lib/prediction-board"
import {
  buildEventGradingRecordSummary,
  buildGradingRecordSummary,
  buildPastReplayRecordSummary,
} from "@/lib/record-summary"
import { gradedPicksToMatchups, gradedPicksToSecondaryBets } from "@/lib/graded-picks-display"
import { dedupeReplayMatchups, dedupeReplaySecondaryBets } from "@/lib/replay-pick-dedupe"
import type {
  GradedTournamentSummary,
  LiveTournamentSnapshot,
  PastSnapshotEvent,
  PredictionRunResponse,
  RecordSummary,
} from "@/lib/types"

import type { PastHistoryLane, PastReplayLane, PastReplaySource } from "./workspace-types"

export function resolvePastHistoryLane(
  lane: PastReplayLane,
  source: PastReplaySource,
): PastHistoryLane | null {
  if (lane === "completed") return null
  if (source === "lab") return lane === "live" ? "lab_live" : "lab_upcoming"
  return lane
}

export function selectDefaultPastEvent(
  options: PastSnapshotEvent[],
  excludeEventId?: string,
  gradingHistory: GradedTournamentSummary[] = [],
  preferredEventId?: string,
): PastSnapshotEvent | null {
  if (options.length === 0) return null
  const excluded = excludeEventId?.trim()
  const candidates = excluded
    ? options.filter((event) => event.event_id !== excluded)
    : options
  const pool = candidates.length > 0 ? candidates : options

  const preferred = preferredEventId?.trim()
  if (preferred) {
    const match = pool.find((event) => event.event_id === preferred)
    if (match) return match
  }

  const gradedByEventId = new Map(
    gradingHistory
      .filter((event) => Boolean(event.event_id))
      .map((event) => [String(event.event_id), event]),
  )
  // Keep API recency order (most recently completed first) — do not sort by graded count,
  // or a prior event with more picks (e.g. U.S. Open) steals default from the latest event.
  const gradedWithPicks = pool.filter(
    (event) => (gradedByEventId.get(event.event_id)?.graded_pick_count ?? 0) > 0,
  )
  if (gradedWithPicks.length > 0) {
    return gradedWithPicks[0] ?? null
  }

  const withSnapshots = pool.filter((event) => (event.snapshot_count ?? 0) > 0)
  return withSnapshots[0] ?? pool[0] ?? null
}

export function useWorkspacePastReplay({
  predictionTab,
  gradingHistory,
  gradingRecordSummary,
  matchupSearch,
  availableBooks,
  pastReplaySource,
  onPastEventContextChange,
  upcomingSourceEventId,
  preferredPastEventId,
}: {
  predictionTab: PredictionTab
  gradingHistory: GradedTournamentSummary[]
  gradingRecordSummary?: RecordSummary
  matchupSearch: string
  availableBooks: string[]
  pastReplaySource: PastReplaySource
  onPastEventContextChange?: (context: { eventName: string; courseName?: string } | null) => void
  upcomingSourceEventId?: string
  /** Latest completed event from dashboard state — default past replay target. */
  preferredPastEventId?: string
}) {
  const [selectedPastEventKey, setSelectedPastEventKey] = useState("")
  const [pastReplaySection, setPastReplaySection] = useState<PastReplayLane>("completed")

  const pastEventsQuery = useQuery({
    queryKey: ["live-refresh-past-events"],
    queryFn: api.getLiveRefreshPastEvents,
    staleTime: 60_000,
    retry: 2,
  })

  useEffect(() => {
    if (predictionTab !== "past") return
    void pastEventsQuery.refetch()
  }, [predictionTab])

  const durableRecordSummary = useMemo(
    () => buildGradingRecordSummary(gradingHistory, gradingRecordSummary),
    [gradingHistory, gradingRecordSummary],
  )

  const fallbackPastEvents = useMemo<PastSnapshotEvent[]>(
    () =>
      gradingHistory
        .filter((event) => Boolean(event.event_id))
        .map((event) => ({
          event_id: String(event.event_id),
          event_name: event.name,
        })),
    [gradingHistory],
  )

  const pastEventOptions = useMemo(() => {
    const persisted = pastEventsQuery.data?.events ?? []
    const merged = new Map<string, PastSnapshotEvent>()
    persisted.forEach((event) => merged.set(event.event_id, event))
    fallbackPastEvents.forEach((event) => {
      if (!merged.has(event.event_id)) merged.set(event.event_id, event)
    })
    return Array.from(merged.values())
  }, [fallbackPastEvents, pastEventsQuery.data?.events])

  const selectedPastEvent = useMemo(() => {
    if (pastEventOptions.length === 0) return null
    if (!selectedPastEventKey) {
      return selectDefaultPastEvent(
        pastEventOptions,
        upcomingSourceEventId,
        gradingHistory,
        preferredPastEventId,
      )
    }
    return (
      pastEventOptions.find((event) => event.event_id === selectedPastEventKey) ??
      selectDefaultPastEvent(
        pastEventOptions,
        upcomingSourceEventId,
        gradingHistory,
        preferredPastEventId,
      )
    )
  }, [gradingHistory, pastEventOptions, preferredPastEventId, selectedPastEventKey, upcomingSourceEventId])

  const pastEventsBootstrapping =
    predictionTab === "past" &&
    pastEventOptions.length === 0 &&
    (pastEventsQuery.isPending || pastEventsQuery.isFetching)

  useEffect(() => {
    if (predictionTab !== "past" || pastEventOptions.length === 0) return
    const defaultEvent = selectDefaultPastEvent(
      pastEventOptions,
      upcomingSourceEventId,
      gradingHistory,
      preferredPastEventId,
    )
    if (!defaultEvent) return
    setSelectedPastEventKey((current) => {
      if (current && pastEventOptions.some((event) => event.event_id === current)) {
        return current
      }
      return defaultEvent.event_id
    })
  }, [gradingHistory, pastEventOptions, preferredPastEventId, predictionTab, upcomingSourceEventId])

  const pastSnapshotQuery = useQuery({
    queryKey: ["live-refresh-past-snapshot", selectedPastEvent?.event_id, pastReplaySection, pastReplaySource],
    queryFn: () =>
      api.getLiveRefreshPastSnapshot(
        selectedPastEvent?.event_id ?? "",
        resolvePastHistoryLane(pastReplaySection, pastReplaySource) ?? "completed",
        { source: pastReplaySource },
      ),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })

  const pastReplayHistoryLane = resolvePastHistoryLane(pastReplaySection, pastReplaySource)
  const pastReplayHasHistoryLanes = pastReplayHistoryLane !== null

  const pastTimelineQuery = useQuery({
    queryKey: ["live-refresh-past-timeline", selectedPastEvent?.event_id, pastReplayHistoryLane],
    queryFn: () => {
      const lane = pastReplayHistoryLane
      if (!lane) {
        throw new Error("Past timeline is only available for live or upcoming lanes.")
      }
      return api.getLiveRefreshPastTimeline(selectedPastEvent?.event_id ?? "", {
        section: lane,
        limit: 24,
      })
    },
    enabled:
      predictionTab === "past" &&
      Boolean(selectedPastEvent?.event_id) &&
      pastReplayHasHistoryLanes,
    staleTime: 30_000,
  })

  const pastMarketRowsQuery = useQuery({
    queryKey: ["live-refresh-past-market-rows", selectedPastEvent?.event_id, pastReplaySection, pastReplaySource],
    queryFn: () =>
      api.getLiveRefreshPastMarketRows(selectedPastEvent?.event_id ?? "", {
        section: pastReplayHistoryLane ?? "completed",
        source: pastReplaySource,
      }),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })

  const pastReplayHasError =
    pastEventsQuery.isError ||
    pastSnapshotQuery.isError ||
    pastTimelineQuery.isError ||
    pastMarketRowsQuery.isError

  const pastReplayErrorMessage =
    (
      pastEventsQuery.error ??
      pastSnapshotQuery.error ??
      pastTimelineQuery.error ??
      pastMarketRowsQuery.error
    ) instanceof Error
      ? (
          pastEventsQuery.error ??
          pastSnapshotQuery.error ??
          pastTimelineQuery.error ??
          pastMarketRowsQuery.error
        )?.message
      : "Replay API request failed."

  const pastSnapshotSection = pastSnapshotQuery.data?.ok
    ? (pastSnapshotQuery.data.snapshot ?? null)
    : null

  const pastLeaderboardForGrades = useMemo(
    () => (predictionTab === "past" ? (pastSnapshotSection?.leaderboard ?? []) : []),
    [pastSnapshotSection?.leaderboard, predictionTab],
  )

  const pastPredictionRun = useMemo(
    () => buildPredictionRunFromSection(pastSnapshotSection),
    [pastSnapshotSection],
  )

  const pastTimelinePoints = useMemo(
    () => (pastTimelineQuery.data?.ok ? (pastTimelineQuery.data.points ?? []) : []),
    [pastTimelineQuery.data],
  )

  const pastMarketRows = useMemo(
    () => (pastMarketRowsQuery.data?.ok ? (pastMarketRowsQuery.data.rows ?? []) : []),
    [pastMarketRowsQuery.data],
  )

  const activePastReplaySnapshotId = pastSnapshotQuery.data?.ok
    ? (pastSnapshotQuery.data.snapshot_id ?? null)
    : null

  const pastReplayRows = useMemo(() => {
    if (!activePastReplaySnapshotId) return pastMarketRows
    const filtered = pastMarketRows.filter((row) => row.snapshot_id === activePastReplaySnapshotId)
    return filtered.length > 0 ? filtered : pastMarketRows
  }, [activePastReplaySnapshotId, pastMarketRows])

  const pastReplayLoading =
    predictionTab === "past" &&
    Boolean(selectedPastEvent?.event_id) &&
    (pastSnapshotQuery.isLoading ||
      pastMarketRowsQuery.isLoading ||
      pastSnapshotQuery.isFetching ||
      pastMarketRowsQuery.isFetching)

  const pastRecentResults = useMemo(() => {
    if (predictionTab !== "past") {
      return gradingHistory.slice(0, 5).map((event) => ({ kind: "graded" as const, event }))
    }
    const gradedByEventId = new Map(
      gradingHistory
        .filter((event) => Boolean(event.event_id))
        .map((event) => [String(event.event_id), event]),
    )
    return pastEventOptions.slice(0, 8).map((event) => {
      const graded = gradedByEventId.get(event.event_id)
      if (graded) return { kind: "graded" as const, event: graded }
      return {
        kind: "replay" as const,
        event: {
          event_id: event.event_id,
          name: event.event_name,
          total_profit: null,
          hits: null,
          graded_pick_count: null,
        },
      }
    })
  }, [gradingHistory, pastEventOptions, predictionTab])

  const selectedEventGrading = useMemo(
    () =>
      gradingHistory.find(
        (event) => String(event.event_id ?? "") === String(selectedPastEvent?.event_id ?? ""),
      ) ?? null,
    [gradingHistory, selectedPastEvent?.event_id],
  )

  const selectedEventGradedMatchups = useMemo(
    () =>
      (selectedEventGrading?.picks ?? []).filter(
        (pick) => String(pick.bet_type ?? "").trim().toLowerCase() === "matchup",
      ),
    [selectedEventGrading?.picks],
  )

  const selectedEventGradedSecondary = useMemo(
    () => gradedPicksToSecondaryBets(selectedEventGrading?.picks ?? []),
    [selectedEventGrading?.picks],
  )

  const useGradedPickInventory =
    pastReplaySection === "completed" && (selectedEventGrading?.picks?.length ?? 0) > 0

  const pastMatchups = useMemo(() => {
    if (useGradedPickInventory) {
      const gradedRows = gradedPicksToMatchups(selectedEventGrading?.picks ?? [])
      return gradedRows.filter((matchup) => {
        const passesSearch = matchupSearch
          ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
          : true
        return passesSearch
      })
    }

    const sourceRows = dedupeReplayMatchups(
      pastReplayRows.length > 0
        ? applyGradedPicksToMatchups(
            buildReplayGeneratedMatchups(pastReplayRows),
            selectedEventGradedMatchups,
          )
        : applyGradedPicksToMatchups(
            pastPredictionRun?.matchup_bets_all_books ?? pastPredictionRun?.matchup_bets ?? [],
            selectedEventGradedMatchups,
          ),
    )
    return sourceRows.filter((matchup) => {
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesSearch
    })
  }, [
    matchupSearch,
    pastPredictionRun,
    pastReplayRows,
    pastReplaySection,
    selectedEventGradedMatchups,
    selectedEventGrading?.picks,
    useGradedPickInventory,
  ])

  const pastSecondaryBets = useMemo(() => {
    if (useGradedPickInventory) {
      return selectedEventGradedSecondary
    }

    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedSecondaryBets(pastReplayRows)
        : flattenSecondaryBets(pastPredictionRun)
    return dedupeReplaySecondaryBets(sourceRows)
  }, [
    pastPredictionRun,
    pastReplayRows,
    pastReplaySection,
    selectedEventGradedSecondary,
    selectedEventGrading?.picks,
    useGradedPickInventory,
  ])

  const displayAvailableBooks = useMemo(() => {
    if (predictionTab !== "past") return availableBooks
    if (useGradedPickInventory) {
      const gradedBooks = new Set<string>()
      for (const pick of selectedEventGrading?.picks ?? []) {
        const normalized = normalizeSportsbook(pick.market_book)
        if (normalized && !NON_BOOK_SOURCES.has(normalized)) gradedBooks.add(normalized)
      }
      if (gradedBooks.size > 0) return Array.from(gradedBooks).sort()
    }
    const replayBooks = new Set<string>()
    pastReplayRows.forEach((row) => {
      const normalized = normalizeSportsbook(row.book)
      if (normalized && !NON_BOOK_SOURCES.has(normalized)) replayBooks.add(normalized)
    })
    if (replayBooks.size > 0) return Array.from(replayBooks).sort()
    return collectAvailableBooks(pastPredictionRun)
  }, [availableBooks, pastPredictionRun, pastReplayRows, predictionTab, selectedEventGrading?.picks, useGradedPickInventory])

  const rawGeneratedMatchups = useMemo(() => {
    if (predictionTab !== "past") return []
    if (useGradedPickInventory) {
      return gradedPicksToMatchups(selectedEventGrading?.picks ?? [])
    }
    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedMatchups(pastReplayRows)
        : getRawGeneratedMatchups(pastPredictionRun)
    return applyGradedPicksToMatchups(sourceRows, selectedEventGradedMatchups)
  }, [
    pastPredictionRun,
    pastReplayRows,
    predictionTab,
    pastReplaySection,
    selectedEventGradedMatchups,
    selectedEventGrading?.picks,
    useGradedPickInventory,
  ])

  const rawGeneratedSecondaryBets = useMemo(() => {
    if (predictionTab !== "past") return []
    if (useGradedPickInventory) {
      return selectedEventGradedSecondary
    }
    return pastReplayRows.length > 0
      ? dedupeReplaySecondaryBets(buildReplayGeneratedSecondaryBets(pastReplayRows))
      : getRawGeneratedSecondaryBets(pastPredictionRun)
  }, [
    pastPredictionRun,
    pastReplayRows,
    predictionTab,
    pastReplaySection,
    selectedEventGradedSecondary,
    selectedEventGrading?.picks,
    useGradedPickInventory,
  ])

  const recordSummary = useMemo(() => {
    if (predictionTab !== "past") {
      return durableRecordSummary
    }

    const officialSummary = buildEventGradingRecordSummary(selectedEventGrading)
    if (officialSummary.combined.picks > 0) {
      return officialSummary
    }

    const dedupedMatchups = dedupeReplayMatchups(rawGeneratedMatchups)
    const dedupedOutrights = dedupeReplaySecondaryBets(rawGeneratedSecondaryBets)
    if (dedupedMatchups.length > 0 || dedupedOutrights.length > 0) {
      return buildPastReplayRecordSummary(
        dedupedMatchups,
        dedupedOutrights,
        pastLeaderboardForGrades,
      )
    }

    return officialSummary
  }, [
    durableRecordSummary,
    pastLeaderboardForGrades,
    predictionTab,
    rawGeneratedMatchups,
    rawGeneratedSecondaryBets,
    selectedEventGrading,
  ])

  const courseName = pastPredictionRun?.course_name ?? ""

  const pastReplayHasData =
    predictionTab === "past" &&
    ((pastPredictionRun?.composite_results?.length ?? 0) > 0 ||
      pastReplayRows.length > 0 ||
      (pastSnapshotSection?.leaderboard?.length ?? 0) > 0 ||
      (selectedEventGrading?.picks?.length ?? 0) > 0)

  useEffect(() => {
    if (!onPastEventContextChange) return
    if (predictionTab !== "past") {
      onPastEventContextChange(null)
      return
    }
    onPastEventContextChange({
      eventName: selectedPastEvent?.event_name ?? "Past event",
      courseName: courseName || undefined,
    })
  }, [courseName, onPastEventContextChange, predictionTab, selectedPastEvent?.event_name])

  return {
    selectedPastEventKey,
    setSelectedPastEventKey,
    pastReplaySection,
    setPastReplaySection,
    pastEventsQuery,
    pastSnapshotQuery,
    pastTimelineQuery,
    pastMarketRowsQuery,
    pastReplayHasHistoryLanes,
    pastReplayHasError,
    pastReplayErrorMessage,
    pastSnapshotSection,
    pastLeaderboardForGrades,
    pastPredictionRun,
    pastTimelinePoints,
    pastReplayRows,
    pastReplayLoading,
    pastRecentResults,
    pastMatchups,
    pastSecondaryBets,
    displayAvailableBooks,
    rawGeneratedMatchups,
    rawGeneratedSecondaryBets,
    recordSummary,
    pastEventOptions,
    selectedPastEvent,
    pastReplayHasData,
    pastEventsBootstrapping,
  }
}

export type WorkspacePastReplay = ReturnType<typeof useWorkspacePastReplay>

export function resolveDisplayPredictionRun(
  predictionTab: PredictionTab,
  predictionRun: PredictionRunResponse | null,
  pastPredictionRun: PredictionRunResponse | null,
) {
  return predictionTab === "past" ? pastPredictionRun : predictionRun
}

export function resolveActiveSection(
  predictionTab: PredictionTab,
  liveTournament: LiveTournamentSnapshot | undefined,
  upcomingTournament: LiveTournamentSnapshot | undefined,
) {
  if (predictionTab === "upcoming") return upcomingTournament
  if (predictionTab === "live") return liveTournament
  return null
}
