import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { CockpitLabPage } from "@/pages/cockpit-lab-page"
import type { PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"

function minimalWorkspaceProps(): PredictionWorkspacePageProps {
  return {
    liveSnapshot: null,
    runtimeStatus: { label: "Live", tone: "good" },
    snapshotNotice: null,
    snapshotAgeSeconds: null,
    predictionTab: "upcoming",
    onPredictionTabChange: () => {},
    availableBooks: [],
    selectedBooks: [],
    onSelectedBooksChange: () => {},
    matchupSearch: "",
    onMatchupSearchChange: () => {},
    minEdge: 0,
    onMinEdgeChange: () => {},
    filteredMatchups: [],
    gradingHistory: [],
    players: [],
    predictionRun: null,
    selectedPlayerKey: "",
    onPlayerSelect: () => {},
    playerProfileState: "unavailable",
    onPlayerProfileRetry: () => {},
    richProfilesEnabled: false,
    secondaryBets: [],
    snapshotBootstrapping: true,
  }
}

describe("lab layout width", () => {
  it("keeps lab workspace as full-width main column (not a side rail)", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CockpitLabPage cockpitWorkspaceProps={minimalWorkspaceProps()} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const root = container.querySelector(".cockpit-lab-root")
    const stripe = container.querySelector("[data-testid='lab-board-lane-stripe']")
    const main = container.querySelector(".cockpit-lab-main")
    const workspace = screen.getByTestId("lab-board-workspace")

    expect(root).toBeTruthy()
    expect(stripe).toBeTruthy()
    expect(main).toBeTruthy()
    // Stripe is decorative sibling; workspace lives inside main (full width), not a 38vw grid track.
    expect(root?.children[0]).toBe(stripe)
    expect(root?.children[1]).toBe(main)
    expect(main?.contains(workspace)).toBe(true)
    expect(workspace.parentElement).toBe(main)
  })
})
