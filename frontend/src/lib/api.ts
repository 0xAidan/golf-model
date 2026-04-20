import type {
  DashboardState,
  EventSummary,
  GradingHistoryResponse,
  LiveRefreshSnapshotResponse,
  LiveRefreshStatusResponse,
  PastMarketRowsResponse,
  PastSnapshotEventsResponse,
  PastSnapshotResponse,
  PastTimelineResponse,
  PlayerProfile,
  PredictionRunRequest,
  PredictionRunResponse,
  ResearchProposal,
  TrackRecordResponse,
} from "@/lib/types"

const JSON_HEADERS = {
  "Content-Type": "application/json",
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

export const api = {
  getDashboardState: () => request<DashboardState>("/api/dashboard/state"),
  getLatestCompletedEvent: () => request<EventSummary>("/api/events/latest-completed"),
  getGradingHistory: () => request<GradingHistoryResponse>("/api/grading/history"),
  getPlayerProfile: (playerKey: string, tournamentId: number, courseNum?: number) =>
    request<PlayerProfile>(
      `/api/players/${playerKey}/profile?tournament_id=${tournamentId}${courseNum === undefined || courseNum === null ? "" : `&course_num=${courseNum}`}`,
    ),
  getPlayerStandaloneProfile: (playerKey: string) =>
    request<StandalonePlayerProfile>(`/api/players/${playerKey}/standalone-profile`),
  searchPlayers: (q: string) =>
    request<{ players: Array<{ player_key: string; player_display: string }> }>(`/api/players/search?q=${encodeURIComponent(q)}`),
  getOutputSummaries: () => request<Record<string, unknown>>("/api/output/latest-summaries"),
  getResearchProposals: () => request<ResearchProposal[]>("/api/research/proposals?limit=12"),
  getAutoresearchStatus: () => request<Record<string, unknown>>("/api/autoresearch/status"),
  getLiveRefreshStatus: () => request<LiveRefreshStatusResponse>("/api/live-refresh/status"),
  getLiveRefreshSnapshot: () => request<LiveRefreshSnapshotResponse>("/api/live-refresh/snapshot"),
  getLiveRefreshPastEvents: () => request<PastSnapshotEventsResponse>("/api/live-refresh/past-events"),
  getLiveRefreshPastSnapshot: (
    eventId: string,
    section: "live" | "upcoming" | "completed" = "completed",
  ) =>
    request<PastSnapshotResponse>(
      `/api/live-refresh/past-snapshot?event_id=${encodeURIComponent(eventId)}&section=${encodeURIComponent(section)}`,
    ),
  getLiveRefreshPastTimeline: (
    eventId: string,
    options?: { section?: "live" | "upcoming"; limit?: number },
  ) => {
    const params = new URLSearchParams({
      event_id: eventId,
      section: options?.section ?? "live",
    })
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    return request<PastTimelineResponse>(`/api/live-refresh/past-timeline?${params.toString()}`)
  },
  getLiveRefreshPastMarketRows: (
    eventId: string,
    options?: {
      marketFamily?: "matchup" | "placement" | string
      section?: "live" | "upcoming"
      limit?: number
    },
  ) => {
    const params = new URLSearchParams({
      event_id: eventId,
    })
    if (options?.marketFamily) {
      params.set("market_family", options.marketFamily)
    }
    if (options?.section) {
      params.set("section", options.section)
    }
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    return request<PastMarketRowsResponse>(`/api/live-refresh/past-market-rows?${params.toString()}`)
  },
  refreshLiveSnapshot: () =>
    request<LiveRefreshSnapshotResponse>("/api/live-refresh/refresh", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({}),
    }),
  startLiveRefresh: (payload?: { tour?: string; live_refresh?: Record<string, unknown> }) =>
    request<Record<string, unknown>>("/api/live-refresh/start", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload ?? {}),
    }),
  patchAutoresearchSettings: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/autoresearch/settings", {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  runPrediction: (payload: PredictionRunRequest) =>
    request<PredictionRunResponse>("/api/simple/upcoming-prediction", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  getTrackRecord: () => request<TrackRecordResponse>("/api/track-record"),
  gradeLatestTournament: (payload?: Partial<EventSummary>) =>
    request<Record<string, unknown>>("/api/grade-tournament", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload ?? {}),
    }),
}
