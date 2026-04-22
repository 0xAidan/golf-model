import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import { isTeamEvent } from "@/lib/event-format"

describe("TeamEventNotice", () => {
  it("renders an upcoming-mode headline and the team-format explanation", () => {
    render(
      <TeamEventNotice
        eventName="Zurich Classic of New Orleans"
        courseName="TPC Louisiana"
        mode="upcoming"
      />,
    )

    expect(screen.getByText(/no bettable card this week/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Zurich Classic of New Orleans · TPC Louisiana/),
    ).toBeInTheDocument()
    // Explanation mentions the team format the pipeline guards against.
    expect(screen.getByText(/Foursomes \+ Fourball/)).toBeInTheDocument()
    // The status grid lists each skipped/not-modelled output.
    expect(screen.getByText(/Placement value bets/)).toBeInTheDocument()
    expect(screen.getByText(/Individual head-to-head matchups/)).toBeInTheDocument()
    expect(screen.getByText(/Pair \/ team matchups/)).toBeInTheDocument()
    expect(screen.getAllByText(/Skipped/)).toHaveLength(3)
    expect(screen.getByText(/Not yet modelled/)).toBeInTheDocument()
    expect(screen.getByText(/Reference only/)).toBeInTheDocument()
  })

  it("uses a live-mode headline when rendered during play", () => {
    render(<TeamEventNotice eventName="Zurich Classic" mode="live" />)
    expect(screen.getByText(/Team event in progress/i)).toBeInTheDocument()
  })

  it("degrades gracefully without event or course name", () => {
    render(<TeamEventNotice mode="upcoming" />)
    expect(screen.getByTestId("team-event-notice")).toBeInTheDocument()
  })
})

describe("isTeamEvent", () => {
  it("returns true only when event_format is exactly 'team'", () => {
    expect(isTeamEvent({ event_format: "team" })).toBe(true)
    expect(isTeamEvent({ event_format: "individual" })).toBe(false)
    expect(isTeamEvent({})).toBe(false)
    expect(isTeamEvent(null)).toBe(false)
    expect(isTeamEvent(undefined)).toBe(false)
  })
})
