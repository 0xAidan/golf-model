import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitCompare } from "lucide-react"
import { useSearchParams } from "react-router-dom"

import { CompareEventDashboard } from "@/components/compare/compare-event-dashboard"
import { CompareEventSelector } from "@/components/compare/compare-event-selector"
import { CompareHistoryDashboard } from "@/components/compare/compare-history-dashboard"
import type { CompareScope } from "@/components/compare/compare-types"
import {
  CURRENT_EVENT_ID,
  useCompareEventData,
  useCompareEventOptions,
} from "@/components/compare/use-compare-event-data"
import { TrackBadge } from "@/components/product/track-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { api } from "@/lib/api"
import { POLLING } from "@/lib/query-polling"
import { useLiveSnapshot } from "@/providers/live-snapshot-provider"
import type { LiveTournamentSnapshot } from "@/lib/types"

const SCOPES: { id: CompareScope; label: string }[] = [
  { id: "event", label: "This event" },
  { id: "history", label: "Track record" },
]

function parseScope(value: string | null): CompareScope {
  return value === "history" ? "history" : "event"
}

export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const scope = parseScope(searchParams.get("scope"))
  const selectedEventId = searchParams.get("event_id") || CURRENT_EVENT_ID

  const { liveTournament, upcomingTournament, labLiveTournament, labUpcomingTournament, isLiveActive } =
    useLiveSnapshot()

  const tracksQuery = useQuery({
    queryKey: ["tracks"],
    queryFn: api.getTracks,
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const { options: eventOptions, isLoading: eventOptionsLoading } = useCompareEventOptions()

  const usingLive = isLiveActive
  const championSection: LiveTournamentSnapshot | undefined = usingLive
    ? liveTournament
    : upcomingTournament
  const challengerSection: LiveTournamentSnapshot | null | undefined = usingLive
    ? labLiveTournament
    : labUpcomingTournament

  const liveTracks = useMemo(
    () => ({
      champion: championSection,
      challenger: challengerSection,
      usingLive,
    }),
    [championSection, challengerSection, usingLive],
  )

  const eventData = useCompareEventData({
    selectedEventId,
    liveTracks,
  })

  const dashboardTrack = tracksQuery.data?.tracks?.dashboard
  const labTrack = tracksQuery.data?.tracks?.lab

  const isCurrent = selectedEventId === CURRENT_EVENT_ID
  const labOff = isCurrent && !challengerSection
  const noEventLoaded = isCurrent && !championSection && !challengerSection

  const contextLine = isCurrent
    ? `${eventData.eventName} · ${eventData.modeLabel}`
    : `${eventData.eventName} · ${eventData.modeLabel}${eventData.gradingEvent ? " · graded" : ""}`

  const handleScopeChange = (next: CompareScope) => {
    const params = new URLSearchParams(searchParams)
    if (next === "event") {
      params.delete("scope")
    } else {
      params.set("scope", next)
    }
    setSearchParams(params, { replace: true })
  }

  const handleEventChange = (eventId: string) => {
    const params = new URLSearchParams(searchParams)
    if (eventId === CURRENT_EVENT_ID) {
      params.delete("event_id")
    } else {
      params.set("event_id", eventId)
    }
    params.delete("scope")
    setSearchParams(params, { replace: true })
  }

  const handleSelectEventFromHistory = (eventId: string) => {
    const params = new URLSearchParams(searchParams)
    params.set("event_id", eventId)
    params.delete("scope")
    setSearchParams(params, { replace: true })
  }

  return (
    <div className="compare-page product-page product-page--satellite" data-testid="compare-page">
      <TerminalPageHeader
        eyebrow="Research"
        title="Track comparison"
        description="Champion vs challenger on any tournament — rankings, picks, and graded outcomes."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <TrackBadge
              track="dashboard"
              variant={eventData.tracks.champion?.model_variant ?? dashboardTrack?.model_variant}
              configHash={dashboardTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.dashboard}
            />
            <span aria-hidden className="text-[var(--text-tertiary)]">
              vs
            </span>
            <TrackBadge
              track="lab"
              variant={eventData.tracks.challenger?.model_variant ?? labTrack?.model_variant}
              configHash={labTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.lab}
            />
          </div>
        }
      />

      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          {scope === "event" ? (
            <CompareEventSelector
              options={eventOptions}
              value={selectedEventId}
              disabled={eventOptionsLoading}
              onChange={handleEventChange}
            />
          ) : null}
          <p className="text-sm font-medium text-[var(--text-secondary)]">{contextLine}</p>
        </div>
        <div className="flex gap-2" role="tablist" aria-label="Compare scope">
          {SCOPES.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={scope === s.id}
              className={`filter-chip${scope === s.id ? " active" : ""}`}
              data-testid={`compare-scope-${s.id}`}
              onClick={() => handleScopeChange(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {scope === "history" ? (
        <CompareHistoryDashboard onSelectEvent={handleSelectEventFromHistory} />
      ) : noEventLoaded ? (
        <div data-testid="compare-no-event">
          <EmptyState
            message="No event loaded"
            description="Switch the dashboard to Upcoming or Live, or pick a past tournament from the dropdown."
            icon={<GitCompare size={24} aria-hidden />}
          />
        </div>
      ) : labOff ? (
        <div className="card compare-panel" data-testid="compare-lab-off">
          <div className="card-body">
            <p className="text-sm text-[var(--text-secondary)]">
              Lab lane is off or has not produced a board for this event yet. Pick a past tournament
              with both tracks, or enable the parallel lab lane and wait for the next live-refresh tick.
            </p>
          </div>
        </div>
      ) : (
        <>
          {!isCurrent && !eventData.isLoading && !eventData.hasRankings ? (
            <div className="card compare-panel" data-testid="compare-past-missing">
              <div className="card-body text-sm text-[var(--text-secondary)]">
                Saved ranking boards are missing for this tournament, but graded pick comparison may
                still be available below.
              </div>
            </div>
          ) : null}
          <CompareEventDashboard
            tracks={eventData.tracks}
            players={eventData.players}
            gradingEvent={eventData.gradingEvent}
            eventName={eventData.eventName}
            eventMode={eventData.eventMode}
            modeLabel={eventData.modeLabel}
            isLoading={eventData.isLoading}
            labAvailable={eventData.labAvailable}
          />
        </>
      )}
    </div>
  )
}

export default ComparePage
