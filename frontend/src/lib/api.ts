import type {
  CalibrationByMarketResponse,
  ChampionChallengerSummary,
  ClvSummaryResponse,
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
  ResearchAbReportResponse,
  ResearchProposal,
  StandalonePlayerProfile,
  TrackRecordResponse,
} from "@/lib/types"

const JSON_HEADERS = {
  "Content-Type": "application/json",
}

const LIVE_REFRESH_STATUS_TIMEOUT_MS = 30_000
const LIVE_REFRESH_SNAPSHOT_TIMEOUT_MS = 35_000
const LIVE_REFRESH_REFRESH_TIMEOUT_MS = 95_000
const LIVE_REFRESH_START_TIMEOUT_MS = 30_000

async function request<T>(path: string, init?: RequestInit, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(path, { signal: controller.signal, ...init })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `Request failed: ${response.status}`)
    }
    return (await response.json()) as T
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`)
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  getChampionChallengerSummary: () =>
    request<ChampionChallengerSummary>("/api/champion-challenger/summary"),
  getDashboardState: () => request<DashboardState>("/api/dashboard/state"),
  getLatestCompletedEvent: () => request<EventSummary>("/api/events/latest-completed"),
  getGradingHistory: (options?: { limit?: number; pickSource?: "all" | "cockpit" | "lab" }) => {
    const params = new URLSearchParams()
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    if (options?.pickSource && options.pickSource !== "all") {
      params.set("pick_source", options.pickSource)
    }
    const qs = params.toString()
    return request<GradingHistoryResponse>(`/api/grading/history${qs ? `?${qs}` : ""}`)
  },
  getPlayerProfile: (playerKey: string, tournamentId: number, courseNum?: number) => {
    const enc = encodeURIComponent(playerKey)
    const qs =
      `tournament_id=${tournamentId}` +
      (courseNum === undefined || courseNum === null ? "" : `&course_num=${courseNum}`)
    return request<PlayerProfile>(`/api/players/${enc}/profile?${qs}`)
  },
  getPlayerStandaloneProfile: (playerKey: string) =>
    request<StandalonePlayerProfile>(
      `/api/players/${encodeURIComponent(playerKey)}/standalone-profile`,
    ),
  searchPlayers: (q: string) =>
    request<{ players: Array<{ player_key: string; player_display: string }> }>(`/api/players/search?q=${encodeURIComponent(q)}`),
  getOutputSummaries: () => request<Record<string, unknown>>("/api/output/latest-summaries"),
  getResearchProposals: () => request<ResearchProposal[]>("/api/research/proposals?limit=12"),
  getAutoresearchStatus: () => request<Record<string, unknown>>("/api/autoresearch/status"),
  getLiveRefreshStatus: () =>
    request<LiveRefreshStatusResponse>(
      "/api/live-refresh/status",
      undefined,
      LIVE_REFRESH_STATUS_TIMEOUT_MS,
    ),
  getLiveRefreshSnapshot: () =>
    request<LiveRefreshSnapshotResponse>(
      "/api/live-refresh/snapshot",
      undefined,
      LIVE_REFRESH_SNAPSHOT_TIMEOUT_MS,
    ),
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
      section?: "live" | "upcoming" | "lab_live" | "lab_upcoming"
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
  postLabLogDisplayedPicks: (body: Record<string, unknown>) =>
    request<{ ok: boolean; rows_written?: number; error?: string }>("/api/lab/log-displayed-picks", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  refreshLiveSnapshot: () =>
    request<LiveRefreshSnapshotResponse>("/api/live-refresh/refresh", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({}),
    }, LIVE_REFRESH_REFRESH_TIMEOUT_MS),
  startLiveRefresh: (payload?: { tour?: string; live_refresh?: Record<string, unknown> }) =>
    request<Record<string, unknown>>("/api/live-refresh/start", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload ?? {}),
    }, LIVE_REFRESH_START_TIMEOUT_MS),
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
  getCalibrationByMarket: () => request<CalibrationByMarketResponse>("/api/calibration/by-market"),
  getClvSummary: () => request<ClvSummaryResponse>("/api/clv/summary"),
  getResearchAbReport: (eventId: string, options?: { persist?: boolean }) => {
    const params = new URLSearchParams({
      event_id: eventId,
      persist: options?.persist === false ? "false" : "true",
    })
    return request<ResearchAbReportResponse>(`/api/research/ab-report?${params.toString()}`)
  },
}
