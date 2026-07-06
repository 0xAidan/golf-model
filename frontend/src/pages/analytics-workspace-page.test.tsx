import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AnalyticsWorkspacePage } from "@/pages/analytics-workspace-page"

const allPicks = [
  {
    pick_key: "pick-rory",
    player_key: "rory-mcilroy",
    player_display: "Rory McIlroy",
    bet_type: "matchup",
    book: "draftkings",
    ev: 0.083,
    profit: 1.25,
    event_name: "John Deere Classic",
  },
  {
    pick_key: "pick-scottie",
    player_key: "scottie-scheffler",
    player_display: "Scottie Scheffler",
    bet_type: "matchup",
    book: "draftkings",
    ev: 0.061,
    profit: -1,
    event_name: "John Deere Classic",
  },
]

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getAnalyticsSummary: vi.fn(async () => ({
      pick_count: 2,
      wins: 1,
      losses: 1,
      pushes: 0,
      graded_count: 2,
      profit_units: 0.25,
      win_rate_pct: 50,
      roi_pct: 12.5,
    })),
    getDashboardState: vi.fn(async () => ({
      ai_status: { available: false },
      latest_completed_event: {
        event_id: "30",
        event_name: "John Deere Classic",
        year: 2026,
      },
    })),
    getAnalyticsPicks: vi.fn(async (params: Record<string, string | number | undefined>) => {
      const picks =
        params.player === "rory-mcilroy"
          ? allPicks.filter((pick) => pick.player_key === "rory-mcilroy")
          : allPicks
      return {
        total: picks.length,
        limit: Number(params.limit ?? picks.length),
        offset: Number(params.offset ?? 0),
        picks,
      }
    }),
    getAnalyticsRollup: vi.fn(async () => ({
      group_by: "event",
      rows: [
        {
          group_key: "30",
          group_label: "John Deere Classic",
          count: 2,
          profit: 0.25,
          roi_pct: 12.5,
        },
      ],
    })),
    exportAnalyticsCsv: vi.fn(async () => "player_display\nRory McIlroy\nScottie Scheffler\n"),
  },
}))

vi.mock("@/lib/api", () => ({
  api: apiMock,
}))

vi.mock("@number-flow/react", () => ({
  default: ({ value }: { value: number }) => <span>{value}</span>,
}))

function renderAnalyticsPage(initialEntry = "/results?tab=analytics") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/results" element={<AnalyticsWorkspacePage />} />
          <Route path="/players/:playerKey" element={<div>Player profile route</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("AnalyticsWorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it("hydrates filters from the URL and re-queries when filters change", async () => {
    const user = userEvent.setup()

    renderAnalyticsPage("/results?tab=analytics&lane=lab&book=dk&from=2026-06-01&to=2026-06-30&event_id=30")

    expect(await screen.findByTestId("analytics-workspace")).toBeInTheDocument()
    expect(screen.getByLabelText("Lane")).toHaveValue("lab")
    expect(screen.getByLabelText("Book")).toHaveValue("dk")
    expect(screen.getByLabelText("From")).toHaveValue("2026-06-01")
    expect(screen.getByLabelText("To")).toHaveValue("2026-06-30")

    await user.type(screen.getByLabelText("Market"), "matchup")

    await waitFor(() => {
      expect(apiMock.getAnalyticsSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({
          lane: "lab",
          book: "dk",
          bet_type: "matchup",
          from: "2026-06-01",
          to: "2026-06-30",
          event_id: "30",
        }),
      )
    })
  })

  it("opens the player sheet without collapsing the main ledger", async () => {
    const user = userEvent.setup()

    renderAnalyticsPage("/results?tab=analytics&event_id=30")

    expect(await screen.findByTestId("analytics-ledger-grid")).toBeInTheDocument()
    expect(await screen.findByText("Rory McIlroy")).toBeInTheDocument()
    expect(await screen.findByText("Scottie Scheffler")).toBeInTheDocument()

    await user.click(screen.getByText("Rory McIlroy"))

    expect(await screen.findByTestId("player-pick-drawer")).toBeInTheDocument()
    expect(screen.getByText("Matching picks from the current analytics filters for this player.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Open full profile" })).toHaveAttribute(
      "href",
      "/players/rory-mcilroy",
    )

    await waitFor(() => {
      expect(apiMock.getAnalyticsPicks).toHaveBeenCalledWith(
        expect.objectContaining({
          event_id: "30",
          player: "rory-mcilroy",
        }),
      )
    })

    expect(screen.getByText("Scottie Scheffler")).toBeInTheDocument()
    expect(screen.getByTestId("analytics-player-history-grid")).toBeInTheDocument()
  })
})
