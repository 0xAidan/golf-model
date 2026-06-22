import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { RouteErrorBoundaryGate } from "@/components/route-error-boundary-gate"
import { ComparePage } from "@/pages/compare-page"

const { apiMock, snapshotMock } = vi.hoisted(() => ({
  apiMock: {
    getTracks: vi.fn(async () => ({
      tracks: {
        dashboard: { track: "dashboard", model_variant: "baseline", config_hash: "011e7743e143e26b" },
        lab: { track: "lab", model_variant: "v5", config_hash: "3936389c4ef2d5b9" },
      },
      effective_config_hash: { dashboard: "011e7743e143e26b", lab: "3936389c4ef2d5b9" },
      history: [],
    })),
    getFieldBoard: vi.fn(async () => ({
      section: "upcoming",
      event_name: "RBC",
      lab_available: true,
      player_count: 2,
      players: [
        {
          player_key: "a",
          player: "Player A",
          champion_rank: 1,
          challenger_rank: 5,
          rank_delta: -4,
          composite: 80,
          course_fit: 1,
          form: 2,
          momentum: 0.1,
          matchup_count: 1,
          in_positive_ev: true,
          has_sg: false,
        },
        {
          player_key: "b",
          player: "Player B",
          champion_rank: 2,
          challenger_rank: 1,
          rank_delta: 1,
          composite: 78,
          course_fit: 1,
          form: 2,
          momentum: 0.1,
          matchup_count: 0,
          in_positive_ev: false,
          has_sg: false,
        },
      ],
    })),
    getLiveRefreshPastEvents: vi.fn(async () => ({
      events: [{ event_id: "26", event_name: "U.S. Open", snapshot_count: 3 }],
    })),
    getLiveRefreshPastSnapshot: vi.fn(async () => ({
      ok: true,
      snapshot: {
        event_name: "U.S. Open",
        rankings: [
          { rank: 1, player_key: "a", player: "Player A", composite: 80, course_fit: 1, form: 2, momentum: 0.1 },
        ],
        matchup_bets: [],
      },
    })),
    getGradingSeason: vi.fn(async () => ({
      year: 2026,
      lane: "all",
      events: [
        {
          event_id: "26",
          name: "U.S. Open",
          event_date: "2026-06-15",
          lanes: {
            dashboard: {
              record: { profit: 10, hit_rate: 0.5, picks: 5, wins: 2, losses: 3, pushes: 0 },
              picks: [],
              graded_pick_count: 5,
              ungraded_positive_ev_count: 0,
              inventory_count: 5,
              status: "graded",
            },
            lab: {
              record: { profit: 8, hit_rate: 0.55, picks: 4, wins: 2, losses: 2, pushes: 0 },
              picks: [],
              graded_pick_count: 4,
              ungraded_positive_ev_count: 0,
              inventory_count: 4,
              status: "graded",
            },
          },
          comparison: {
            profit_delta: -2,
            hit_rate_delta: 0.05,
            picks_only_dashboard: 1,
            picks_only_lab: 0,
            overlap_matchups: 3,
          },
        },
      ],
      tournaments: [],
      summary: {
        dashboard: { profit: 10, hit_rate: 0.5, picks: 5, wins: 2, losses: 3, pushes: 0 },
        lab: { profit: 8, hit_rate: 0.55, picks: 4, wins: 2, losses: 2, pushes: 0 },
        comparison: {
          profit_delta: -2,
          hit_rate_delta: 0.05,
          picks_only_dashboard: 1,
          picks_only_lab: 0,
          overlap_matchups: 3,
        },
      },
    })),
    getTrackComparison: vi.fn(async () => ({
      window: "30d",
      window_days: 30,
      tracks: {
        cockpit: {
          n: 10,
          graded_with_odds: 10,
          wins: 5,
          hit_rate_pct: 50,
          roi_pct: 5,
          pnl_units: 0.5,
          brier: 0.2,
          low_sample: true,
        },
        lab: {
          n: 12,
          graded_with_odds: 12,
          wins: 7,
          hit_rate_pct: 58.33,
          roi_pct: 8,
          pnl_units: 0.96,
          brier: 0.19,
          low_sample: true,
        },
      },
      overlap: { both: 4, cockpit_only: 3, lab_only: 5 },
      by_market: {
        cockpit: { matchup: { n: 8, roi_pct: 6, hit_rate_pct: 50 } },
        lab: { matchup: { n: 9, roi_pct: 9, hit_rate_pct: 55 } },
      },
      data_kind: "live_graded",
      note: "Live graded +EV picks only.",
    })),
  },
  snapshotMock: { value: {} as Record<string, unknown> },
}))

vi.mock("@/components/compare/compare-charts-lazy", () => ({
  RankScatterChartLazy: () => <div data-testid="compare-rank-scatter-mock" />,
  ComponentDriversChartLazy: () => <div data-testid="compare-component-chart-mock" />,
  MarketDeltaChartLazy: () => <div data-testid="compare-market-chart-mock" />,
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))
vi.mock("@/providers/live-snapshot-provider", () => ({
  useLiveSnapshot: () => snapshotMock.value,
}))

function renderPage(initialEntry = "/compare") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ComparePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function ThrowOnBroken(): never {
  throw new Error("Failed to fetch dynamically imported module")
}

describe("ComparePage", () => {
  it("shows the lab-off notice when the challenger section is missing", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: { event_name: "RBC", rankings: [], matchup_bets: [] },
      labLiveTournament: null,
      labUpcomingTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-page")).toBeInTheDocument())
    expect(screen.getByTestId("compare-lab-off")).toBeInTheDocument()
  })

  it("shows no-event empty state when both tracks lack snapshot sections", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: undefined,
      labLiveTournament: null,
      labUpcomingTournament: null,
    }
    renderPage()
    expect(await screen.findByTestId("compare-no-event")).toBeInTheDocument()
  })

  it("renders event analytics when both tracks are present", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: {
        event_name: "RBC",
        model_variant: "baseline",
        rankings: [
          { rank: 1, player_key: "a", player: "Player A", composite: 80, course_fit: 0, form: 0, momentum: 0 },
          { rank: 2, player_key: "b", player: "Player B", composite: 78, course_fit: 0, form: 0, momentum: 0 },
        ],
        matchup_bets: [
          {
            pick: "A",
            pick_key: "a",
            opponent: "B",
            opponent_key: "b",
            odds: "-110",
            model_win_prob: 0.55,
            implied_prob: 0.52,
            ev: 0.06,
            ev_pct: "6%",
            composite_gap: 2,
            form_gap: 1,
            course_fit_gap: 1,
            reason: "x",
          },
        ],
      },
      labUpcomingTournament: {
        event_name: "RBC",
        model_variant: "v5",
        rankings: [
          { rank: 5, player_key: "a", player: "Player A", composite: 70, course_fit: 0, form: 0, momentum: 0 },
          { rank: 1, player_key: "b", player: "Player B", composite: 82, course_fit: 0, form: 0, momentum: 0 },
        ],
        matchup_bets: [
          {
            pick: "C",
            pick_key: "c",
            opponent: "D",
            opponent_key: "d",
            odds: "+120",
            model_win_prob: 0.5,
            implied_prob: 0.45,
            ev: 0.1,
            ev_pct: "10%",
            composite_gap: 1,
            form_gap: 0,
            course_fit_gap: 0,
            reason: "y",
          },
        ],
      },
      labLiveTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-event-dashboard")).toBeInTheDocument())
    expect(screen.getByTestId("compare-kpi-band")).toBeInTheDocument()
    expect(screen.getByTestId("compare-matchup-diff")).toBeInTheDocument()
    expect(screen.getByTestId("compare-matchup-grid")).toBeInTheDocument()
    expect(screen.getByText("Champ EV")).toBeInTheDocument()
    expect(screen.getByTestId("track-badge-dashboard")).toBeInTheDocument()
    expect(screen.getByTestId("track-badge-lab")).toBeInTheDocument()
  })

  it("renders track record scope from query param", async () => {
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: undefined,
      labLiveTournament: null,
      labUpcomingTournament: null,
    }
    renderPage("/compare?scope=history")
    await waitFor(() => expect(screen.getByTestId("compare-history-dashboard")).toBeInTheDocument())
    expect(screen.getByTestId("track-metrics-dashboard")).toBeInTheDocument()
    expect(screen.getByTestId("compare-history-overlap")).toBeInTheDocument()
  })

  it("switches to track record via scope toggle", async () => {
    const user = userEvent.setup()
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: {
        event_name: "RBC",
        rankings: [],
        matchup_bets: [],
      },
      labUpcomingTournament: {
        event_name: "RBC",
        rankings: [],
        matchup_bets: [],
      },
      labLiveTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-event-dashboard")).toBeInTheDocument())
    await user.click(screen.getByTestId("compare-scope-history"))
    await waitFor(() => expect(screen.getByTestId("compare-history-dashboard")).toBeInTheDocument())
    expect(screen.getByTestId("compare-season-events-section")).toBeInTheDocument()
  })

  it("loads a past tournament from the event selector", async () => {
    const user = userEvent.setup()
    snapshotMock.value = {
      isLiveActive: false,
      liveTournament: undefined,
      upcomingTournament: {
        event_name: "RBC",
        rankings: [],
        matchup_bets: [],
      },
      labUpcomingTournament: {
        event_name: "RBC",
        rankings: [],
        matchup_bets: [],
      },
      labLiveTournament: null,
    }
    renderPage()
    await waitFor(() => expect(screen.getByTestId("compare-event-select")).not.toBeDisabled())
    await waitFor(() =>
      expect(screen.getByTestId("compare-event-select")).toHaveTextContent("U.S. Open"),
    )
    await user.selectOptions(screen.getByTestId("compare-event-select"), "26")
    await waitFor(() => expect(screen.getByTestId("compare-event-dashboard")).toBeInTheDocument())
    expect(screen.getByText("U.S. Open · Completed · graded")).toBeInTheDocument()
  })
})

describe("Route error boundary on satellite routes", () => {
  it("shows chunk failure fallback with reload affordance", () => {
    render(
      <MemoryRouter initialEntries={["/broken"]}>
        <RouteErrorBoundaryGate>
          <Routes>
            <Route path="/broken" element={<ThrowOnBroken />} />
          </Routes>
        </RouteErrorBoundaryGate>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("route-error-boundary")).toHaveAttribute("data-chunk-failure", "true")
    expect(screen.getByTestId("route-error-reload")).toBeInTheDocument()
  })

  it("resets after navigating to a healthy route", async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={["/broken"]}>
        <RouteErrorBoundaryGate>
          <Routes>
            <Route path="/broken" element={<ThrowOnBroken />} />
            <Route path="/ok" element={<div data-testid="ok-page">OK</div>} />
          </Routes>
        </RouteErrorBoundaryGate>
      </MemoryRouter>,
    )

    expect(screen.getByTestId("route-error-boundary")).toBeInTheDocument()
    window.history.pushState({}, "", "/ok")
    await user.click(document.body)
    render(
      <MemoryRouter initialEntries={["/ok"]}>
        <RouteErrorBoundaryGate>
          <Routes>
            <Route path="/ok" element={<div data-testid="ok-page">OK</div>} />
          </Routes>
        </RouteErrorBoundaryGate>
      </MemoryRouter>,
    )
    expect(screen.getByTestId("ok-page")).toBeInTheDocument()
  })
})
