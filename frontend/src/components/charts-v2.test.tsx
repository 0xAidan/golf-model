import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { RollingBarLine } from "./charts-v2"

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

describe("RollingBarLine", () => {
  const baseEvents = [
    { event_name: "Event A", event_completed: "2026-04-10", avg_sg_total: 1.1, fin_text: "T3" },
    { event_name: "Event B", event_completed: "2026-04-03", avg_sg_total: -0.4, fin_text: "T18" },
  ]

  it("disables tabs with no event aggregates", () => {
    render(<RollingBarLine events={baseEvents} trendSeries={[0.3, -0.1, 0.2]} />)

    expect(screen.getByRole("button", { name: "TOTAL" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "APP" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "T2G" })).toBeDisabled()
  })

  it("enables round-series tabs when rounds view has data", async () => {
    const user = userEvent.setup()
    render(
      <RollingBarLine
        events={baseEvents}
        trendSeries={[0.3, -0.1, 0.2]}
        roundSeriesByMetric={{
          APP: [0.4, 0.1, -0.2],
          T2G: [1.0, 0.7, -0.1],
        }}
      />,
    )

    await user.click(screen.getByRole("button", { name: "ROUNDS" }))

    expect(screen.getByRole("button", { name: "TOTAL" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "APP" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "T2G" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "PUTT" })).toBeDisabled()
  })
})

