import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { LegacyModelPage } from "@/pages/legacy-model-page"
import type { LiveRefreshSnapshot } from "@/lib/types"

function renderPage(snapshot: LiveRefreshSnapshot | null) {
  render(
    <MemoryRouter>
      <LegacyModelPage liveSnapshot={snapshot} />
    </MemoryRouter>,
  )
}

describe("LegacyModelPage", () => {
  it("shows the shared empty state when no legacy snapshot is present", () => {
    renderPage(null)

    expect(screen.getByTestId("legacy-model-page")).toBeInTheDocument()
    expect(screen.getByText("Legacy baseline snapshot is not available yet.")).toBeInTheDocument()
  })

  it("renders legacy ranking and matchup grids when snapshot data exists", () => {
    const snapshot = {
      legacy_tournament: {
        event_name: "RBC Heritage",
        model_variant: "baseline",
        generated_from: "legacy_baseline_model",
        rankings: [
          {
            player_key: "player_a",
            player: "Player A",
            rank: 1,
            composite: 80.1,
            course_fit: 79.4,
            form: 78.2,
            momentum: 0.4,
          },
        ],
        matchup_bets: [
          {
            pick_key: "player_a",
            opponent_key: "player_b",
            pick: "Player A",
            opponent: "Player B",
            book: "bet365",
            odds: "-110",
            ev_pct: "6.0%",
            tier: "GOOD",
          },
        ],
        diagnostics: {
          errors: [],
        },
      },
    } as unknown as LiveRefreshSnapshot

    renderPage(snapshot)

    expect(screen.getByTestId("legacy-model-bento")).toBeInTheDocument()
    expect(screen.getByTestId("legacy-rankings-grid")).toBeInTheDocument()
    expect(screen.getByTestId("legacy-matchups-grid")).toBeInTheDocument()
  })
})
