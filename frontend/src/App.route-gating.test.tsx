import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { ThemeProvider } from "@/components/theme-provider"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getDashboardState: vi.fn(async () => ({})),
    getGradingSeason: vi.fn(async () => ({ year: 2026, lane: "cockpit", events: [], tournaments: [], summary: { dashboard: { picks: 0, wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: null }, lab: { picks: 0, wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: null }, comparison: { profit_delta: 0, hit_rate_delta: 0, picks_only_dashboard: 0, picks_only_lab: 0, overlap_matchups: 0 } } })),
    getLiveRefreshStatus: vi.fn(async () => ({ status: { running: false } })),
    getLiveRefreshSnapshot: vi.fn(async () => ({ snapshot: null, age_seconds: null })),
    getLiveRefreshSummary: vi.fn(async () => ({ snapshot: null, age_seconds: null, data_state: "missing" })),
    getPlayerProfile: vi.fn(async () => null),
    gradeLatestTournament: vi.fn(async () => ({})),
    startGradeJob: vi.fn(async () => ({ job_id: "test-job", status: "running" })),
    getOpsJob: vi.fn(async () => ({ id: "test-job", status: "complete", progress_pct: 100 })),
    refreshLiveSnapshot: vi.fn(async () => ({ ok: false })),
  },
}))

vi.mock("@/lib/api", () => ({
  api: apiMock,
}))

vi.mock("@/hooks/use-live-refresh-runtime", () => ({
  useLiveRefreshRuntime: () => undefined,
}))

vi.mock("@/hooks/use-prediction-tab", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-prediction-tab")>("@/hooks/use-prediction-tab")

  return {
    ...actual,
    usePredictionTab: () => ({
      predictionTab: "past" as const,
      setPredictionTab: vi.fn(),
    }),
  }
})

function renderAppAtRoute(route: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

describe("App legacy route replay gating", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // /matchups redirects to dashboard ?tab=full-picks (Phase 4 lane merge).
  it("redirects /matchups to the dashboard home route", async () => {
    renderAppAtRoute("/matchups")

    await waitFor(() => {
      expect(screen.getByTestId("monitoring-shell-main")).toBeInTheDocument()
    })
    expect(screen.queryByText("Legacy matchups route unavailable in replay mode")).not.toBeInTheDocument()
  })

  it("redirects /grading to /results", async () => {
    renderAppAtRoute("/grading")

    await waitFor(() => {
      expect(screen.getByTestId("results-page")).toBeInTheDocument()
    })
  })

  it("renders /system health page", async () => {
    renderAppAtRoute("/system")

    await waitFor(() => {
      expect(screen.getByTestId("system-page")).toBeInTheDocument()
    })
  })

  it("defers grading-season includePicks on dashboard boot", async () => {
    renderAppAtRoute("/")

    await waitFor(() => {
      expect(apiMock.getGradingSeason).toHaveBeenCalledWith(
        expect.objectContaining({ lane: "cockpit", includePicks: false, limit: 20 }),
      )
    })
  })

  it("loads grading-season with picks on /results", async () => {
    renderAppAtRoute("/results")

    await waitFor(() => {
      expect(apiMock.getGradingSeason).toHaveBeenCalledWith(
        expect.objectContaining({ includePicks: true, limit: 100 }),
      )
    })
  })
})
