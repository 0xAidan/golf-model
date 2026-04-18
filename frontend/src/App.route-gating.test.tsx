import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import App from "@/App"

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
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("App legacy route replay gating", () => {
  it.each([
    ["/players", "Legacy players route unavailable in replay mode"],
    ["/matchups", "Legacy matchups route unavailable in replay mode"],
    ["/course", "Legacy course route unavailable in replay mode"],
  ])("shows replay-safe messaging on %s", async (route: string, title: string) => {
    renderAppAtRoute(route)

    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /return to cockpit home/i })).toBeInTheDocument()
  })
})
