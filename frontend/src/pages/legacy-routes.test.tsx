import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import React from "react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import gradingHistoryFixture from "@/__fixtures__/grading-history.json"
import { GradingPage } from "@/pages/legacy-routes"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getGradingHistory: vi.fn(),
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
    apiMock.getGradingHistory.mockResolvedValue(gradingHistoryFixture)

    renderGradingPage()

    expect(await screen.findByTestId("grading-trust-strip")).toBeInTheDocument()
    expect(screen.getByTestId("grading-source-cockpit")).toBeInTheDocument()
    expect(await screen.findByTestId("grading-ungraded-banner")).toHaveTextContent(/\+EV pick/i)
  })

  it("refetches history when pick source changes", async () => {
    apiMock.getGradingHistory.mockResolvedValue(gradingHistoryFixture)
    const user = userEvent.setup()

    renderGradingPage()
    await screen.findByTestId("grading-trust-strip")

    await user.click(screen.getByTestId("grading-source-lab"))

    await waitFor(() => {
      expect(apiMock.getGradingHistory).toHaveBeenCalledWith({ pickSource: "lab" })
    })
  })
})
