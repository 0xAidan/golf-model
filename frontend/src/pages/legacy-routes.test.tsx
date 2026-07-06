import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import React from "react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import gradingHistoryFixture from "@/__fixtures__/grading-history.json"
import type { GradingSeasonResponse, TrackRecordPick } from "@/lib/types"
import { GradingPage } from "@/pages/legacy-routes"

const emptyBucket = {
  picks: 0,
  wins: 0,
  losses: 0,
  pushes: 0,
  profit: 0,
  hit_rate: null,
}

const toSeasonFixture = (
  fixture: typeof gradingHistoryFixture,
  lane: "all" | "dashboard" | "lab" = "dashboard",
): GradingSeasonResponse => ({
  year: 2026,
  lane,
  events: fixture.tournaments.map((event) => ({
    ...event,
    has_results: true,
    lanes: {
      dashboard: {
        inventory_count: event.graded_pick_count ?? 0,
        graded_pick_count: event.graded_pick_count ?? 0,
        ungraded_positive_ev_count: 0,
        status: "graded" as const,
        record: {
          picks: event.graded_pick_count ?? 0,
          wins: event.hits ?? 0,
          losses: 0,
          pushes: 0,
          profit: event.total_profit ?? 0,
          hit_rate: null,
        },
        picks: (event.picks ?? []) as TrackRecordPick[],
        hits: event.hits,
        total_profit: event.total_profit,
      },
      lab: {
        inventory_count: 0,
        graded_pick_count: 0,
        ungraded_positive_ev_count: 0,
        status: "graded" as const,
        record: emptyBucket,
        picks: [],
        hits: 0,
        total_profit: 0,
      },
    },
    comparison: {
      profit_delta: event.total_profit ?? 0,
      hit_rate_delta: 0,
      picks_only_dashboard: event.graded_pick_count ?? 0,
      picks_only_lab: 0,
      overlap_matchups: 0,
    },
  })) as GradingSeasonResponse["events"],
  tournaments: [],
  summary: {
    dashboard: fixture.summary?.combined ?? emptyBucket,
    lab: emptyBucket,
    comparison: {
      profit_delta: fixture.summary?.combined?.profit ?? 0,
      hit_rate_delta: 0,
      picks_only_dashboard: fixture.summary?.combined?.picks ?? 0,
      picks_only_lab: 0,
      overlap_matchups: 0,
    },
  },
})

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getGradingSeason: vi.fn(),
    getDashboardState: vi.fn(async () => ({
      ai_status: { available: false },
      latest_graded_tournament: {
        name: "RBC Heritage",
        event_id: "512",
        picks_count: 3,
        graded_pick_count: 1,
        last_graded_at: "2026-04-20T18:45:00Z",
      },
      latest_completed_event: {
        event_id: "512",
        event_name: "RBC Heritage",
        year: 2026,
      },
    })),
    getLiveRefreshStatus: vi.fn(async () => ({ status: {} })),
  },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))

vi.mock("@number-flow/react", () => ({
  default: ({ value }: { value: number }) => <span>{value}</span>,
}))

vi.mock("@/components/charts-bar-lazy", () => ({
  BarTrendChartLazy: () => <div data-testid="bar-trend-chart-mock" />,
}))

vi.mock("@/components/charts", () => ({
  BarTrendChart: () => <div data-testid="bar-trend-chart-mock" />,
}))

function renderGradingPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GradingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("GradingPage", () => {
  it("renders trust strip, source toggle, and ungraded banner", async () => {
    const season = toSeasonFixture(gradingHistoryFixture)
    if (season.events[0]?.lanes?.dashboard) {
      season.events[0].lanes.dashboard.ungraded_positive_ev_count = 2
    }
    apiMock.getGradingSeason.mockResolvedValue(season)

    renderGradingPage()

    expect(await screen.findByTestId("grading-trust-strip")).toBeInTheDocument()
    expect(screen.getByTestId("grading-source-cockpit")).toBeInTheDocument()
    expect(await screen.findByTestId("grading-ungraded-banner")).toHaveTextContent(/\+EV pick/i)
  })

  it("refetches season when pick source changes", async () => {
    apiMock.getGradingSeason.mockResolvedValue(toSeasonFixture(gradingHistoryFixture))
    const user = userEvent.setup()

    renderGradingPage()
    await screen.findByTestId("grading-trust-strip")

    await user.click(screen.getByTestId("grading-source-lab"))

    await waitFor(() => {
      expect(apiMock.getGradingSeason).toHaveBeenCalledWith(
        expect.objectContaining({ lane: "lab", year: 2026 }),
      )
    })
  })

  it("renders the season grid and expands pick detail rows", async () => {
    apiMock.getGradingSeason.mockResolvedValue(toSeasonFixture(gradingHistoryFixture))
    const user = userEvent.setup()

    renderGradingPage()

    expect(await screen.findByTestId("grading-season-grid")).toBeInTheDocument()

    const firstEvent = gradingHistoryFixture.tournaments[0]
    expect(firstEvent).toBeDefined()

    const detailToggle = await screen.findByTestId(
      `grading-detail-toggle-${firstEvent?.event_id}-${firstEvent?.year}`,
    )
    await user.click(detailToggle)

    expect(await screen.findByText("Dashboard picks")).toBeInTheDocument()
    expect(await screen.findAllByTestId("pick-row")).not.toHaveLength(0)
  })
})
