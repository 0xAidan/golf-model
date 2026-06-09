import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { PlayersPage } from "@/pages/players-page"
import type { PlayersPageProps } from "@/pages/players-page"

const standaloneProfile = {
  player_key: "wyndham_clark",
  player_display: "Wyndham Clark",
  header: {
    player_display: "Wyndham Clark",
    dg_rank: 24,
    owgr_rank: 37,
    dg_skill_estimate: 1.25,
    rounds_in_db: 120,
    events_tracked: 34,
  },
  sg_skills: {
    sg_total: 1.194,
    sg_ott: 0.2,
    sg_app: 0.8,
    sg_arg: 0.1,
    sg_putt: 0.09,
  },
  approach_buckets: [],
  rolling_windows: { "10": 3.353, "25": 1.614, "50": 0.833 },
  rolling_windows_expanded: {
    sg_total: { "10": 3.353, "25": 1.614, "50": 0.833 },
    sg_ott: { "10": 0.1, "25": 0.1, "50": 0.1 },
    sg_app: { "10": 1.2, "25": 0.8, "50": 0.5 },
    sg_arg: { "10": 0.1, "25": 0.1, "50": 0.1 },
    sg_putt: { "10": 0.1, "25": 0.1, "50": 0.1 },
    sg_t2g: { "10": 1.5, "25": 1.0, "50": 0.7 },
  },
  trend_series: [0.5, 0.8, 1.0, 1.2],
  recent_events: [],
  has_skill_data: true,
  has_ranking_data: true,
  has_approach_data: false,
}

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

vi.mock("@/components/charts-v2", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/charts-v2")>()
  return {
    ...actual,
    PentagonRadar: () => <div data-testid="pentagon-radar-mock" />,
    BeeswarmStrip: () => <div data-testid="beeswarm-mock" />,
    RollingBarLine: () => <div data-testid="rolling-bar-mock" />,
    HistoryTable: () => <div data-testid="history-table-mock" />,
    ApproachArcGauges: () => <div data-testid="approach-gauges-mock" />,
  }
})

vi.mock("@/components/charts", () => ({
  SparklineChart: () => <div data-testid="sparkline-mock" />,
}))

vi.mock("@/lib/api", () => ({
  api: {
    getPlayerStandaloneProfile: vi.fn(async () => standaloneProfile),
    getPlayerProfile: vi.fn(async () => ({
      player_key: "wyndham_clark",
      player_display: "Wyndham Clark",
      current_metrics: {},
      recent_rounds: [],
      course_history: [],
      linked_bets: [],
    })),
    searchPlayers: vi.fn(async () => ({ players: [] })),
  },
}))

function buildProps(): PlayersPageProps {
  return {
    players: [
      {
        player_key: "wyndham_clark",
        player_display: "Wyndham Clark",
        rank: 3,
        composite: 71.5,
        form: 89.2,
        course_fit: 57.2,
        momentum: 50,
        momentum_trend: 22.6,
      },
    ],
    liveSnapshot: {
      generated_at: "2026-06-09T12:00:00Z",
      live_tournament: {
        event_name: "Memorial Tournament",
        course_name: "Muirfield Village",
        field_size: 156,
        tournament_id: 42,
        active: true,
        diagnostics: { state: "edges_available" },
      },
    },
    snapshotNotice: null,
    snapshotAgeSeconds: 30,
    predictionTab: "live",
    tournamentId: 42,
    courseNum: 1,
    selectedPlayerKey: "wyndham_clark",
    onPlayerSelect: vi.fn(),
    filteredMatchups: [],
    secondaryBets: [],
    minEdge: 0.02,
    richProfilesEnabled: true,
  }
}

function renderPage(props = buildProps()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/players?player=wyndham_clark"]}>
        <PlayersPage {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("PlayersPage", () => {
  it("renders command center with event header and player profile", async () => {
    renderPage()
    expect(screen.getByTestId("players-page")).toBeInTheDocument()
    expect(screen.getByTestId("event-command-header")).toBeInTheDocument()
    expect(screen.getByText("Memorial Tournament")).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByTestId("players-profile-panel")).toBeInTheDocument()
    })

    expect(screen.getByTestId("players-identity-hero")).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Wyndham Clark" })).toBeInTheDocument()
    expect(screen.getByTestId("players-bento-grid")).toBeInTheDocument()
    expect(screen.getByTestId("players-insight-summary")).toBeInTheDocument()
  })

  it("renders field explorer with player cards", () => {
    renderPage()
    expect(screen.getByTestId("players-field-explorer")).toBeInTheDocument()
    expect(screen.getByTestId("field-card-wyndham_clark")).toBeInTheDocument()
  })
})
