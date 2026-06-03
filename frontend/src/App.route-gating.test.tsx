import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { ThemeProvider } from "@/components/theme-provider"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getDashboardState: vi.fn(async () => ({})),
    getGradingHistory: vi.fn(async () => ({ tournaments: [] })),
    getLiveRefreshStatus: vi.fn(async () => ({ status: { running: false } })),
    getLiveRefreshSnapshot: vi.fn(async () => ({ snapshot: null, age_seconds: null })),
    getPlayerProfile: vi.fn(async () => null),
    gradeLatestTournament: vi.fn(async () => ({})),
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

  // /players was intentionally un-gated in commit da76a05 (standalone profile
  // page no longer depends on tournament_id), so it is no longer in the gated
  // set. /matchups remains gated until the dashboard home route covers the
  // replay-aware variant.
  it.each([
    ["/matchups", "Legacy matchups route unavailable in replay mode"],
  ])("shows replay-safe messaging on %s", async (route: string, title: string) => {
    renderAppAtRoute(route)

    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /return to dashboard home/i })).toBeInTheDocument()
  })

  it("keeps dashboard and lab grading records on separate sources", async () => {
    renderAppAtRoute("/lab")

    await waitFor(() => {
      expect(apiMock.getGradingHistory).toHaveBeenCalledWith({ pickSource: "lab" })
    })

    vi.clearAllMocks()
    renderAppAtRoute("/")

    await waitFor(() => {
      expect(apiMock.getGradingHistory).toHaveBeenCalledWith({ pickSource: "cockpit" })
    })
  })
})
