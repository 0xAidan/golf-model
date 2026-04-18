import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { LegacyRouteGate } from "@/pages/legacy-route-gate"

describe("LegacyRouteGate", () => {
  it("shows honest replay messaging for the legacy players route in past mode", () => {
    render(
      <MemoryRouter>
        <LegacyRouteGate route="players" mode="past">
          <div>legacy players content</div>
        </LegacyRouteGate>
      </MemoryRouter>,
    )

    expect(screen.getByText("Legacy players route unavailable in replay mode")).toBeInTheDocument()
    expect(screen.getByText(/Use the cockpit home route for replay-aware rankings, spotlight, and player context\./i)).toBeInTheDocument()
    expect(screen.queryByText("legacy players content")).not.toBeInTheDocument()
  })

  it("shows honest replay messaging for the legacy matchups route in past mode", () => {
    render(
      <MemoryRouter>
        <LegacyRouteGate route="matchups" mode="past">
          <div>legacy matchups content</div>
        </LegacyRouteGate>
      </MemoryRouter>,
    )

    expect(screen.getByText("Legacy matchups route unavailable in replay mode")).toBeInTheDocument()
    expect(screen.getByText(/Use the cockpit home route for stored matchup replay, featured edges, and the full generated picks inventory\./i)).toBeInTheDocument()
    expect(screen.queryByText("legacy matchups content")).not.toBeInTheDocument()
  })

  it("shows honest replay messaging for the legacy course route in past mode", () => {
    render(
      <MemoryRouter>
        <LegacyRouteGate route="course" mode="past">
          <div>legacy course content</div>
        </LegacyRouteGate>
      </MemoryRouter>,
    )

    expect(screen.getByText("Legacy course route unavailable in replay mode")).toBeInTheDocument()
    expect(screen.getByText(/Use the cockpit home route for replay-aware course context, weather\/feed framing, and stored event diagnostics\./i)).toBeInTheDocument()
    expect(screen.queryByText("legacy course content")).not.toBeInTheDocument()
  })

  it("renders the route content outside replay mode", () => {
    render(
      <MemoryRouter>
        <LegacyRouteGate route="players" mode="upcoming">
          <div>legacy players content</div>
        </LegacyRouteGate>
      </MemoryRouter>,
    )

    expect(screen.getByText("legacy players content")).toBeInTheDocument()
    expect(screen.queryByText("Legacy players route unavailable in replay mode")).not.toBeInTheDocument()
  })
})
