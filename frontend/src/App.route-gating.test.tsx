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
  // /players was intentionally un-gated in commit da76a05 (standalone profile
  // page no longer depends on tournament_id), so it is no longer in the gated
  // set. /matchups and /course remain gated until the cockpit-home route
  // covers their replay-aware variants.
  it.each([
    ["/matchups", "Legacy matchups route unavailable in replay mode"],
    ["/course", "Legacy course route unavailable in replay mode"],
  ])("shows replay-safe messaging on %s", async (route: string, title: string) => {
    renderAppAtRoute(route)

    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /return to cockpit home/i })).toBeInTheDocument()
  })
})
