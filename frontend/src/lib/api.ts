import type {
  DashboardState,
  EventSummary,
  GradingHistoryResponse,
  PlayerProfile,
  PredictionRunRequest,
  PredictionRunResponse,
  ResearchProposal,
  ScheduleEvent,
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
  getScheduleEvents: (tour: string) => request<{ events: ScheduleEvent[] }>(`/api/events/schedule?tour=${tour}`),
  getGradingHistory: () => request<GradingHistoryResponse>("/api/grading/history"),
  getPlayerProfile: (playerKey: string, tournamentId: number, courseNum?: number) =>
    request<PlayerProfile>(
      `/api/players/${playerKey}/profile?tournament_id=${tournamentId}${courseNum ? `&course_num=${courseNum}` : ""}`,
    ),
  getOutputSummaries: () => request<Record<string, unknown>>("/api/output/latest-summaries"),
  getResearchProposals: () => request<ResearchProposal[]>("/api/research/proposals?limit=12"),
  getAutoresearchStatus: () => request<Record<string, unknown>>("/api/autoresearch/status"),
  runPrediction: (payload: PredictionRunRequest) =>
    request<PredictionRunResponse>("/api/simple/upcoming-prediction", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  gradeLatestTournament: (payload?: Partial<EventSummary>) =>
    request<Record<string, unknown>>("/api/grade-tournament", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload ?? {}),
    }),
}
