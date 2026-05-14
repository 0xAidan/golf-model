import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { SuiteShell } from "@/components/shell"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"

describe("SuiteShell", () => {
  it("keeps the mode switch visible alongside suite navigation", () => {
    render(
      <MemoryRouter>
        <SuiteShell
          headline="RBC Heritage"
          subheadline="One dashboard for live, upcoming, and replay context."
          modeSwitcher={<div>Live / Upcoming / Past</div>}
          frameStatus={<div>Runtime active · 12s old</div>}
          actions={<button type="button">Refresh now</button>}
        >
          <div>Dashboard body</div>
        </SuiteShell>
      </MemoryRouter>,
    )

    expect(screen.getByText("Live / Upcoming / Past")).toBeInTheDocument()
    expect(screen.getByTestId("nav-prediction")).toBeInTheDocument()
    expect(screen.getByTestId("nav-lab-board")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /players/i })).toBeInTheDocument()
    expect(screen.getByTestId("nav-matchups")).toBeInTheDocument()
    expect(screen.getByText("Runtime active · 12s old")).toBeInTheDocument()
    expect(screen.getByText("Dashboard body")).toBeInTheDocument()
  })
})

describe("CockpitWorkspace", () => {
  it("locks in the suite blueprint zones and core module placeholders", () => {
    render(
      <CockpitWorkspace
        leftRail={
          <>
            <CockpitModule title="Event switchboard" description="Mode and event selection." />
            <CockpitModule title="Context rail" description="Course, feed, and replay entry points." />
          </>
        }
        center={
          <>
            <CockpitModule title="Event headline" description="Primary tournament framing." />
            <CockpitModule title="Featured top plays" description="Highest-conviction opportunities." />
            <CockpitModule title="All generated picks" description="Complete algorithm output." />
            <CockpitModule title="Leaderboard" description="Live or replay standings." />
            <CockpitModule title="Power rankings" description="Model board and drill-in points." />
            <CockpitModule title="Market intel" description="Secondary pricing context." />
          </>
        }
        rightRail={
          <>
            <CockpitModule
              title="Player spotlight"
              description="Selected player summary and deep profile space."
              emptyState="Select a player from the dashboard to load the spotlight."
            />
            <CockpitModule title="Diagnostics / grading context" description="System health and review lane." />
          </>
        }
      />,
    )

    // "Left area" / "Center modules" / "Right rail" placeholder labels were
    // removed when the workspace shell collapsed to a borderless three-column
    // layout; test now asserts on the real module titles rendered in each rail.
    expect(screen.getByText("Event switchboard")).toBeInTheDocument()
    expect(screen.getByText("Context rail")).toBeInTheDocument()
    expect(screen.getByText("Event headline")).toBeInTheDocument()
    expect(screen.getByText("Featured top plays")).toBeInTheDocument()
    expect(screen.getByText("All generated picks")).toBeInTheDocument()
    expect(screen.getByText("Leaderboard")).toBeInTheDocument()
    expect(screen.getByText("Power rankings")).toBeInTheDocument()
    expect(screen.getByText("Market intel")).toBeInTheDocument()
    expect(screen.getByText("Player spotlight")).toBeInTheDocument()
    expect(screen.getByText("Select a player from the dashboard to load the spotlight.")).toBeInTheDocument()
    expect(screen.getByText("Diagnostics / grading context")).toBeInTheDocument()
  })

  it("stack layout can surface center modules before the left rail when stackMainFirst is set", () => {
    const { container } = render(
      <CockpitWorkspace
        layout="stack"
        stackMainFirst
        leftRail={<div data-testid="rail-left">Left rail</div>}
        center={<div data-testid="rail-center">Center rail</div>}
        rightRail={<div data-testid="rail-right">Right rail</div>}
      />,
    )
    const zones = container.querySelectorAll(".cockpit-stacked-zone")
    expect(zones.length).toBe(3)
    expect(zones[0].querySelector("[data-testid='rail-center']")).toBeTruthy()
    expect(zones[1].querySelector("[data-testid='rail-left']")).toBeTruthy()
    expect(zones[2].querySelector("[data-testid='rail-right']")).toBeTruthy()
  })
})
