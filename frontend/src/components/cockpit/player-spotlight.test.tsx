import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import type { CockpitSpotlightModel } from "@/lib/cockpit-spotlight"

vi.mock("@/components/player-profile-sections", () => ({
  PlayerProfileSections: () => <div>Mock profile sections</div>,
}))

const spotlight: CockpitSpotlightModel = {
  playerKey: "scottie_scheffler",
  playerName: "Scottie Scheffler",
  eventName: "RBC Heritage",
  mode: "upcoming",
  modeLabel: "Upcoming",
  sourceBadges: ["Rankings", "Generated picks"],
  narrative: "Scottie Scheffler matters on the pre-tournament board.",
  headerStats: [
    { label: "Model rank", value: "#1" },
    { label: "Composite", value: "92.4" },
  ],
  summaryStats: [
    { label: "Best fit now", value: "Form" },
    { label: "Secondary markets", value: "1" },
  ],
  inventoryNotes: [
    { label: "Best secondary market", detail: "Top 10 +110 at draftkings (5.0% EV)" },
  ],
}

describe("PlayerSpotlightPanel", () => {
  it("renders a non-blank empty state when no spotlight is available", () => {
    render(
      <PlayerSpotlightPanel
        spotlight={null}
        player={null}
        profile={undefined}
        profileReady={false}
        richProfilesEnabled={false}
      />,
    )

    expect(
      screen.getByText("Select a player from rankings, leaderboard, featured plays, or generated picks to load the shared spotlight."),
    ).toBeInTheDocument()
  })

  it("renders spotlight context even when no ranking row is attached", () => {
    render(
      <PlayerSpotlightPanel
        spotlight={spotlight}
        player={null}
        profile={undefined}
        profileReady={false}
        richProfilesEnabled={false}
      />,
    )

    expect(screen.getByText("Scottie Scheffler")).toBeInTheDocument()
    expect(screen.getByText("Why this player matters now")).toBeInTheDocument()
    expect(
      screen.getByText("This player is available through cockpit context, but no ranking row is attached for the embedded rich profile drill-down yet."),
    ).toBeInTheDocument()
  })
})
