import type {
  CalibrationByMarketResponse,
  ChampionChallengerSummary,
  ClvSummaryResponse,
  DashboardState,
  DataHealthReport,
  FieldBoardResponse,
  PromotionReadinessResponse,
  TrackComparisonResponse,
  EventSummary,
  GradingHistoryResponse,
  GradingEventPicksResponse,
  GradingSeasonResponse,
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
  TracksResponse,
} from "@/lib/types"

const JSON_HEADERS = {
  "Content-Type": "application/json",
}

const LIVE_REFRESH_STATUS_TIMEOUT_MS = 30_000
const LIVE_REFRESH_SNAPSHOT_TIMEOUT_MS = 35_000
const LIVE_REFRESH_REFRESH_TIMEOUT_MS = 95_000
const LIVE_REFRESH_START_TIMEOUT_MS = 30_000
const PAST_REPLAY_TIMEOUT_MS = 90_000
const GRADING_SEASON_TIMEOUT_MS = 120_000
const GRADE_TOURNAMENT_TIMEOUT_MS = 180_000
/** Lab instrumentation panels; allow headroom when dashboard is busy with live-refresh recompute. */
const RESEARCH_INSTRUMENTATION_TIMEOUT_MS = 30_000

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
  getTracks: () => request<TracksResponse>("/api/tracks"),
  getFieldBoard: (section: "auto" | "live" | "upcoming" = "auto") =>
    request<FieldBoardResponse>(`/api/players/field-board?section=${section}`),
  getPromotionReadiness: () =>
    request<PromotionReadinessResponse>("/api/tracks/promotion-readiness"),
  getTrackComparison: (window: "30d" | "90d" | "season" = "30d") =>
    request<TrackComparisonResponse>(`/api/eval/track-comparison?window=${window}`),
  promoteTrack: (body: { reason: string; from_track?: string }) =>
    request<Record<string, unknown>>("/api/tracks/promote", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  rollbackTrack: (body: { track?: string } = {}) =>
    request<Record<string, unknown>>("/api/tracks/rollback", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  getDataHealth: (year = 2026) =>
    request<DataHealthReport>(`/api/data-health?year=${year}`),
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
  getGradingSeason: (options?: {
    year?: number
    lane?: "all" | "cockpit" | "lab"
    includePicks?: boolean
    includeReconciliation?: boolean
    limit?: number
  }) => {
    const params = new URLSearchParams()
    if (options?.year !== undefined) {
      params.set("year", String(options.year))
    }
    if (options?.lane && options.lane !== "all") {
      params.set("lane", options.lane)
    }
    if (options?.includePicks === false) {
      params.set("include_picks", "false")
    }
    if (options?.includeReconciliation) {
      params.set("include_reconciliation", "true")
    }
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    const qs = params.toString()
    return request<GradingSeasonResponse>(
      `/api/grading/season${qs ? `?${qs}` : ""}`,
      undefined,
      GRADING_SEASON_TIMEOUT_MS,
    )
  },
  getGradingEventPicks: (options: { eventId: string; year?: number; lane?: "cockpit" | "dashboard" | "lab" }) => {
    const params = new URLSearchParams({
      event_id: options.eventId,
    })
    if (options.year !== undefined) {
      params.set("year", String(options.year))
    }
    if (options.lane) {
      params.set("lane", options.lane)
    }
    return request<GradingEventPicksResponse>(
      `/api/grading/event-picks?${params.toString()}`,
      undefined,
      GRADING_SEASON_TIMEOUT_MS,
    )
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
  getLiveRefreshSummary: () =>
    request<LiveRefreshSnapshotResponse>(
      "/api/live-refresh/summary",
      undefined,
      LIVE_REFRESH_SNAPSHOT_TIMEOUT_MS,
    ),
  getLiveRefreshPastEvents: () =>
    request<PastSnapshotEventsResponse>("/api/live-refresh/past-events", undefined, PAST_REPLAY_TIMEOUT_MS),
  getLiveRefreshPastSnapshot: (
    eventId: string,
    section: "live" | "upcoming" | "lab_live" | "lab_upcoming" | "completed" = "completed",
    options?: { source?: "dashboard" | "lab" },
  ) =>
    request<PastSnapshotResponse>(
      `/api/live-refresh/past-snapshot?event_id=${encodeURIComponent(eventId)}&section=${encodeURIComponent(section)}${
        options?.source ? `&source=${encodeURIComponent(options.source)}` : ""
      }`,
      undefined,
      PAST_REPLAY_TIMEOUT_MS,
    ),
  getLiveRefreshPastTimeline: (
    eventId: string,
    options?: { section?: "live" | "upcoming" | "lab_live" | "lab_upcoming"; limit?: number },
  ) => {
    const params = new URLSearchParams({
      event_id: eventId,
      section: options?.section ?? "live",
    })
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    return request<PastTimelineResponse>(`/api/live-refresh/past-timeline?${params.toString()}`, undefined, PAST_REPLAY_TIMEOUT_MS)
  },
  getLiveRefreshPastMarketRows: (
    eventId: string,
    options?: {
      marketFamily?: "matchup" | "placement" | string
      section?: "live" | "upcoming" | "lab_live" | "lab_upcoming" | "completed"
      source?: "dashboard" | "lab"
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
    if (options?.source) {
      params.set("source", options.source)
    }
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit))
    }
    return request<PastMarketRowsResponse>(`/api/live-refresh/past-market-rows?${params.toString()}`, undefined, PAST_REPLAY_TIMEOUT_MS)
  },
  postLabLogDisplayedPicks: (body: Record<string, unknown>) =>
    request<{ ok: boolean; rows_written?: number; error?: string }>("/api/lab/log-displayed-picks", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  refreshLiveSnapshot: async (): Promise<LiveRefreshSnapshotResponse> => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), LIVE_REFRESH_REFRESH_TIMEOUT_MS)
    try {
      const response = await fetch("/api/live-refresh/refresh", {
        method: "POST",
        headers: JSON_HEADERS,
        signal: controller.signal,
        body: JSON.stringify({}),
      })
      const text = await response.text()
      let body: LiveRefreshSnapshotResponse
      try {
        body = JSON.parse(text || "{}") as LiveRefreshSnapshotResponse
      } catch {
        throw new Error(text || `Request failed: ${response.status}`)
      }
      if (response.status === 409) {
        return { ...body, ok: false, busy: true }
      }
      if (response.status === 202) {
        return { ...body, ok: true, accepted: true }
      }
      if (response.status === 503) {
        return { ...body, ok: false }
      }
      if (!response.ok) {
        throw new Error(text || `Request failed: ${response.status}`)
      }
      return body
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        throw new Error(`Request timed out after ${LIVE_REFRESH_REFRESH_TIMEOUT_MS / 1000}s`)
      }
      throw err
    } finally {
      clearTimeout(timer)
    }
  },
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
    request<Record<string, unknown>>(
      "/api/grade-tournament",
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(payload ?? {}),
      },
      GRADE_TOURNAMENT_TIMEOUT_MS,
    ),
  startGradeJob: (payload?: Partial<EventSummary>) =>
    request<{ job_id: string; status: string; message?: string }>(
      "/api/ops/jobs/grade",
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(payload ?? {}),
      },
      15_000,
    ),
  getOpsJob: (jobId: string) =>
    request<{
      id: string
      status: string
      progress_pct: number
      message?: string
      result?: Record<string, unknown>
      error?: string
    }>(`/api/ops/jobs/${encodeURIComponent(jobId)}`),
  getAnalyticsSummary: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    })
    return request<{
      pick_count: number
      wins: number
      losses: number
      pushes: number
      graded_count: number
      profit_units: number
      win_rate_pct: number
      roi_pct: number
    }>(`/api/analytics/summary?${qs.toString()}`)
  },
  getAnalyticsPicks: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    })
    return request<{ total: number; limit: number; offset: number; picks: Record<string, unknown>[] }>(
      `/api/analytics/picks?${qs.toString()}`,
    )
  },
  getAnalyticsRollup: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    })
    return request<{ group_by: string; rows: Record<string, unknown>[] }>(
      `/api/analytics/picks/rollup?${qs.toString()}`,
    )
  },
  exportAnalyticsCsv: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v))
    })
    qs.set("format", "csv")
    qs.set("limit", "5000")
    return fetch(`/api/analytics/picks?${qs.toString()}`).then(async (r) => {
      if (!r.ok) throw new Error(await r.text())
      return r.text()
    })
  },
  getCalibrationByMarket: () =>
    request<CalibrationByMarketResponse>(
      "/api/calibration/by-market",
      undefined,
      RESEARCH_INSTRUMENTATION_TIMEOUT_MS,
    ),
  getClvSummary: () =>
    request<ClvSummaryResponse>("/api/clv/summary", undefined, RESEARCH_INSTRUMENTATION_TIMEOUT_MS),
  getOpsHealth: () => request<Record<string, unknown>>("/api/ops/health"),
  getResearchAbReport: (eventId: string, options?: { persist?: boolean }) => {
    const params = new URLSearchParams({
      event_id: eventId,
      persist: options?.persist === false ? "false" : "true",
    })
    return request<ResearchAbReportResponse>(
      `/api/research/ab-report?${params.toString()}`,
      undefined,
      RESEARCH_INSTRUMENTATION_TIMEOUT_MS,
    )
  },
}
