import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { PredictionWorkspacePage } from "@/pages/prediction-workspace-page"
import type { PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getLiveRefreshPastEvents: vi.fn(async () => ({ events: [] })),
    getLiveRefreshPastSnapshot: vi.fn(async () => ({ ok: false, snapshot: null })),
    getLiveRefreshPastTimeline: vi.fn(async () => ({ ok: false, points: [] })),
    getLiveRefreshPastMarketRows: vi.fn(async () => ({ ok: false, rows: [] })),
  },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))

function buildProps(): PredictionWorkspacePageProps {
  return {
    liveSnapshot: {
      generated_at: "2026-06-04T16:00:00Z",
      live_tournament: {
        event_name: "RBC Heritage",
        active: true,
        diagnostics: { state: "edges_available" },
        live_opportunity_alerts: [
          {
            opportunity_key: "matchup|tournament_matchups|a|b|fanduel|+110",
            market_type: "tournament_matchups",
            player: "Player A",
            ev: 0.12,
          },
        ],
        leaderboard: [
          {
            rank: 3,
            position: "T3",
            player_key: "player_a",
            player: "Player A",
            total_to_par: -8,
            start_leaderboard_position: "T15",
            leaderboard_delta: 12,
          },
        ],
        frozen_pre_teeoff_rankings: [
          {
            rank: 12,
            player_key: "player_a",
            player: "Player A",
            composite: 72.1,
            course_fit: 70,
            form: 69,
            momentum: 68,
          },
        ],
      },
    },
    runtimeStatus: { label: "Live", tone: "good" },
    snapshotNotice: null,
    snapshotAgeSeconds: 5,
    predictionTab: "live",
    onPredictionTabChange: vi.fn(),
    availableBooks: ["fanduel"],
    selectedBooks: [],
    onSelectedBooksChange: vi.fn(),
    matchupSearch: "",
    onMatchupSearchChange: vi.fn(),
    minEdge: 0.02,
    onMinEdgeChange: vi.fn(),
    filteredMatchups: [
      {
        pick: "Player A",
        pick_key: "player_a",
        opponent: "Player B",
        opponent_key: "player_b",
        odds: "+110",
        book: "fanduel",
        model_win_prob: 0.56,
        implied_prob: 0.5,
        ev: 0.12,
        ev_pct: "12.0%",
        composite_gap: 2,
        form_gap: 1,
        course_fit_gap: 1,
        reason: "Edge",
        is_new_live_opportunity: true,
        first_seen_at: "2026-06-04T16:00:00Z",
      },
    ],
    gradingHistory: [],
    players: [
      {
        player_key: "player_a",
        player_display: "Player A",
        rank: 4,
        composite: 78.9,
        course_fit: 70,
        form: 69,
        momentum: 68,
        start_rank: 12,
        current_rank: 4,
        rank_delta: 8,
        leaderboard_position: "T3",
        start_leaderboard_position: "T15",
        leaderboard_delta: 12,
        total_to_par: -8,
      },
    ],
    predictionRun: {
      status: "hydrated",
      event_name: "RBC Heritage",
      composite_results: [],
      matchup_bets: [],
      value_bets: {},
    },
    selectedPlayerKey: "player_a",
    onPlayerSelect: vi.fn(),
    selectedPlayerProfile: undefined,
    playerProfileState: "unavailable",
    playerProfileErrorMessage: undefined,
    onPlayerProfileRetry: vi.fn(),
    richProfilesEnabled: false,
    secondaryBets: [
      {
        market: "Top 10",
        player: "Player A",
        player_display: "Player A",
        player_key: "player_a",
        odds: "+450",
        ev: 0.11,
        book: "fanduel",
        is_new_live_opportunity: true,
        first_seen_at: "2026-06-04T16:00:00Z",
      },
    ],
    powerRankingsSubtitle: null,
    pastReplaySource: "dashboard",
    onPastEventContextChange: vi.fn(),
  }
}

function renderPage(props: PredictionWorkspacePageProps) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PredictionWorkspacePage {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("PredictionWorkspacePage live UX", () => {
  it("renders dual model/scoring ranking columns", () => {
    renderPage(buildProps())

    expect(screen.getByText("Model now")).toBeInTheDocument()
    expect(screen.getByText("Start (model)")).toBeInTheDocument()
    expect(screen.getByText("Model Δ")).toBeInTheDocument()
    expect(screen.getAllByText("Pos").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Start pos").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Pos Δ").length).toBeGreaterThan(0)
    expect(screen.getAllByText("To par").length).toBeGreaterThan(0)
  })

  it("shows alert strip count and NEW LIVE badges", () => {
    renderPage(buildProps())

    expect(screen.getByTestId("live-opportunity-alert-strip")).toHaveTextContent(/1 new live opportunity/i)
    expect(screen.getAllByText("NEW LIVE").length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "New this refresh" })).toBeInTheDocument()
  })
})
