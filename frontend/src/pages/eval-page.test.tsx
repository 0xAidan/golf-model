import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { EvalPage } from "@/pages/eval-page"

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getPromotionReadiness: vi.fn(),
    promoteTrack: vi.fn(),
    rollbackTrack: vi.fn(),
  },
}))

vi.mock("@/lib/api", () => ({ api: apiMock }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <EvalPage />
    </QueryClientProvider>,
  )
}

describe("EvalPage promotion tab", () => {
  it("shows the disabled note and keeps the promote button disabled when promotion is off", async () => {
    apiMock.getPromotionReadiness.mockResolvedValue({
      promotion_enabled: false,
      passed: false,
      gates: [{ id: "charter_live_gates", passed: false, detail: "minimum_bets_not_met" }],
    })
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId("promotion-gate-charter_live_gates")).toBeInTheDocument(),
    )
    expect(screen.getByTestId("promotion-disabled-note")).toBeInTheDocument()
    expect(screen.getByTestId("promotion-promote-btn")).toBeDisabled()
  })

  it("requires reason + confirmation phrase before enabling promote when gates pass", async () => {
    apiMock.getPromotionReadiness.mockResolvedValue({
      promotion_enabled: true,
      passed: true,
      gates: [
        { id: "charter_live_gates", passed: true, detail: "all charter gates pass" },
        { id: "lab_graded_sample", passed: true, detail: "120 graded +EV lab picks" },
      ],
    })
    renderPage()
    await waitFor(() => expect(screen.getByTestId("promotion-promote-btn")).toBeInTheDocument())
    // Still disabled with no reason/confirm.
    expect(screen.getByTestId("promotion-promote-btn")).toBeDisabled()
    fireEvent.change(screen.getByTestId("promotion-reason"), { target: { value: "soak passed" } })
    fireEvent.change(screen.getByTestId("promotion-confirm"), { target: { value: "PROMOTE" } })
    expect(screen.getByTestId("promotion-promote-btn")).not.toBeDisabled()
  })
})
