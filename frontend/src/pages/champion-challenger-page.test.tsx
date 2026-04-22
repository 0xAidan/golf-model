import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChampionChallengerPage } from "@/pages/champion-challenger-page"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getChampionChallengerSummary: vi.fn(async () => ({
      champion: "v4.2",
      challengers: ["stub_v0"],
      windows_days: [14, 30],
      models: [
        {
          model_name: "v4.2",
          windows: {
            "14": {
              brier: { model_name: "v4.2", brier: 0.18, n: 12 },
              matchup_roi: { model_name: "v4.2", bets: 4, staked: 4, pnl: 0.4, roi_pct: 10 },
              clv: { model_name: "v4.2", clv_bps: 50, n: 4 },
            },
            "30": {
              brier: { model_name: "v4.2", brier: 0.2, n: 30 },
              matchup_roi: { model_name: "v4.2", bets: 10, staked: 10, pnl: 0.5, roi_pct: 5 },
              clv: { model_name: "v4.2", clv_bps: 35, n: 10 },
            },
          },
        },
        {
          model_name: "stub_v0",
          windows: {
            "14": {
              brier: { model_name: "stub_v0", brier: null, n: 0 },
              matchup_roi: {
                model_name: "stub_v0",
                bets: 0,
                staked: 0,
                pnl: 0,
                roi_pct: null,
              },
              clv: { model_name: "stub_v0", clv_bps: null, n: 0 },
            },
            "30": {
              brier: { model_name: "stub_v0", brier: 0.25, n: 6 },
              matchup_roi: {
                model_name: "stub_v0",
                bets: 3,
                staked: 3,
                pnl: -0.3,
                roi_pct: -10,
              },
              clv: { model_name: "stub_v0", clv_bps: -20, n: 3 },
            },
          },
        },
      ],
    })),
  },
}))

vi.mock("@/lib/api", () => ({
  api: apiMock,
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ChampionChallengerPage />
    </QueryClientProvider>,
  )
}

describe("ChampionChallengerPage", () => {
  it("renders one row per model returned by the API", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId("champion-challenger-table")).toBeInTheDocument(),
    )
    expect(screen.getByTestId("champion-challenger-row-v4.2")).toBeInTheDocument()
    expect(screen.getByTestId("champion-challenger-row-stub_v0")).toBeInTheDocument()
    expect(screen.getByText(/Champion:/)).toBeInTheDocument()
    expect(screen.getAllByText(/stub_v0/).length).toBeGreaterThanOrEqual(1)
  })

  it("renders the 30d ROI percentage for the champion", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId("champion-challenger-row-v4.2")).toBeInTheDocument(),
    )
    const champRow = screen.getByTestId("champion-challenger-row-v4.2")
    expect(champRow).toHaveTextContent("10.00%") // 14d
    expect(champRow).toHaveTextContent("5.00%") // 30d
    expect(champRow).toHaveTextContent("35.0 bps") // 30d CLV
  })
})
