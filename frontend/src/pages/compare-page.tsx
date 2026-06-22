import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitCompare } from "lucide-react"
import { useSearchParams } from "react-router-dom"

import { CompareEventDashboard } from "@/components/compare/compare-event-dashboard"
import { CompareHistoryDashboard } from "@/components/compare/compare-history-dashboard"
import type { CompareScope } from "@/components/compare/compare-types"
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

  const { liveTournament, upcomingTournament, labLiveTournament, labUpcomingTournament, isLiveActive } =
    useLiveSnapshot()

  const tracksQuery = useQuery({
    queryKey: ["tracks"],
    queryFn: api.getTracks,
    refetchInterval: POLLING.dashboard,
    staleTime: POLLING.queryDefaultStale,
  })

  const usingLive = isLiveActive
  const championSection: LiveTournamentSnapshot | undefined = usingLive
    ? liveTournament
    : upcomingTournament
  const challengerSection: LiveTournamentSnapshot | null | undefined = usingLive
    ? labLiveTournament
    : labUpcomingTournament

  const dashboardTrack = tracksQuery.data?.tracks?.dashboard
  const labTrack = tracksQuery.data?.tracks?.lab

  const trackSections = useMemo(
    () => ({
      champion: championSection,
      challenger: challengerSection,
      usingLive,
    }),
    [championSection, challengerSection, usingLive],
  )

  const eventName = championSection?.event_name || challengerSection?.event_name || "current event"
  const labOff = !challengerSection
  const noEventLoaded = !championSection && !challengerSection

  const handleScopeChange = (next: CompareScope) => {
    if (next === "event") {
      searchParams.delete("scope")
      setSearchParams(searchParams, { replace: true })
      return
    }
    setSearchParams({ scope: next }, { replace: true })
  }

  return (
    <div className="product-page product-page--satellite" data-testid="compare-page">
      <TerminalPageHeader
        eyebrow="Research"
        title="Track comparison"
        description="Same event, both model tracks. Differences are informational — not a recommendation to switch."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <TrackBadge
              track="dashboard"
              variant={championSection?.model_variant ?? dashboardTrack?.model_variant}
              configHash={dashboardTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.dashboard}
            />
            <span aria-hidden className="text-[var(--text-tertiary)]">
              vs
            </span>
            <TrackBadge
              track="lab"
              variant={challengerSection?.model_variant ?? labTrack?.model_variant}
              configHash={labTrack?.config_hash ?? tracksQuery.data?.effective_config_hash?.lab}
            />
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-[var(--text-secondary)]">
          {eventName} · {usingLive ? "Live" : "Upcoming"}
        </p>
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
        <CompareHistoryDashboard />
      ) : noEventLoaded ? (
        <div data-testid="compare-no-event">
          <EmptyState
            message="No event loaded"
            description="Switch the dashboard to Upcoming or Live, or open Lab when the parallel lane is enabled."
            icon={<GitCompare size={24} aria-hidden />}
          />
        </div>
      ) : labOff ? (
        <div className="card" data-testid="compare-lab-off">
          <div className="card-body">
            <p className="text-sm text-[var(--text-secondary)]">
              Lab lane is off or has not produced a board for this event yet, so there is nothing to
              compare. Enable the parallel lab lane (<code>LIVE_REFRESH_LAB_PROFILE_ENABLED=1</code>) and
              wait for the next live-refresh tick. See the Lab page for lane status.
            </p>
          </div>
        </div>
      ) : (
        <CompareEventDashboard tracks={trackSections} />
      )}
    </div>
  )
}

export default ComparePage
