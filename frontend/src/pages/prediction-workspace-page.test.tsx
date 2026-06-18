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
    selectedPlayerKey: "",
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
  it("renders dual model/scoring ranking columns in live mode", async () => {
    renderPage(buildProps())

    const grid = screen.getByTestId("cockpit-rankings-grid")
    expect(grid).toHaveTextContent("Model now")
    expect(grid).not.toHaveTextContent("Start (model)")
    expect(grid).not.toHaveTextContent("Model Δ")
    expect(grid).toHaveTextContent("Pos")
    expect(grid).not.toHaveTextContent("Start pos")
    expect(grid).toHaveTextContent("Pos Δ")
    expect(grid).toHaveTextContent("To par")
  })

  it("renders model-centric ranking columns in upcoming mode", async () => {
    const props = buildProps()
    props.predictionTab = "upcoming"
    props.players = [
      {
        player_key: "player_a",
        player_display: "Player A",
        rank: 1,
        composite: 82,
        course_fit: 78,
        form: 80,
        momentum: 76,
        momentum_trend: 0.4,
        momentum_direction: "hot",
      },
    ]
    renderPage(props)

    expect(screen.getByText("Form")).toBeInTheDocument()
    expect(screen.getByText("Course")).toBeInTheDocument()
    expect(screen.getByText("Mom.")).toBeInTheDocument()
    expect(screen.getByText("SG Traj")).toBeInTheDocument()
    expect(screen.queryByText("Model Δ")).not.toBeInTheDocument()
    expect(screen.queryByText("To par")).not.toBeInTheDocument()
  })

  it("shows alert strip count and NEW LIVE badges", () => {
    renderPage(buildProps())

    expect(screen.getByTestId("live-opportunity-alert-strip")).toHaveTextContent(/1 new live opportunity/i)
    expect(screen.getAllByText("NEW LIVE").length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "New this refresh" })).toBeInTheDocument()
  })

  it("renders model-centric columns in past mode", async () => {
    apiMock.getLiveRefreshPastSnapshot.mockResolvedValue({
      ok: true,
      snapshot: {
        event_name: "Past Open",
        rankings: [
          {
            rank: 1,
            player_key: "player_a",
            player: "Player A",
            composite: 82,
            course_fit: 78,
            form: 80,
            momentum: 76,
          },
        ],
        diagnostics: { state: "edges_available" },
      },
    } as never)
    apiMock.getLiveRefreshPastMarketRows.mockResolvedValue({ ok: true, rows: [] })

    const props = buildProps()
    props.predictionTab = "past"
    props.gradingHistory = [
      {
        event_id: "500",
        name: "Past Open",
        total_profit: 0,
        graded_pick_count: 0,
      },
    ]
    renderPage(props)

    const grid = await screen.findByTestId("cockpit-rankings-grid")
    expect(grid).toHaveTextContent("Form")
    expect(grid).not.toHaveTextContent("Model Δ")
  })

  it("shows hydration fallback banner when section cross-falls back", () => {
    const props = buildProps()
    props.predictionRun = {
      ...props.predictionRun!,
      hydration_section: "upcoming_fallback_live",
    }
    renderPage(props)

    expect(screen.getByTestId("hydration-fallback-banner")).toHaveTextContent(/upcoming view is showing live/i)
  })

  it("shows team event notice in live mode for team-format snapshots", () => {
    const props = buildProps()
    props.liveSnapshot = {
      ...props.liveSnapshot!,
      live_tournament: {
        ...props.liveSnapshot!.live_tournament!,
        event_name: "Zurich Classic",
        event_format: "team",
        diagnostics: { state: "team_event" },
      },
    }
    renderPage(props)

    expect(screen.getByTestId("team-event-notice")).toBeInTheDocument()
    expect(screen.getByTestId("team-event-notice")).toHaveTextContent(/team/i)
  })

  it("shows eligibility warning banner when rankings withheld", () => {
    const props = buildProps()
    props.predictionTab = "upcoming"
    props.players = []
    props.predictionRun = {
      status: "hydrated",
      event_name: "Test Event",
      composite_results: [],
      matchup_bets: [],
      value_bets: {},
      warnings: ["Rankings withheld: field eligibility not verified."],
      hydration_section: "upcoming",
    }
    renderPage(props)

    expect(screen.getByTestId("eligibility-warning-banner")).toHaveTextContent(/eligibility not verified/i)
  })

  it("shows snapshot notice once via lane trust banner", () => {
    const props = buildProps()
    props.snapshotNotice = "Snapshot is stale — last refresh failed."
    renderPage(props)

    expect(screen.getByTestId("trust-status-banner")).toHaveTextContent(/snapshot is stale/i)
    expect(screen.queryAllByText(/snapshot is stale/i)).toHaveLength(1)
  })
})
