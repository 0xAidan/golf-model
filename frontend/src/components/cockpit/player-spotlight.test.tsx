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

    // Empty-state copy was tightened during the cockpit redesign — the panel
    // now renders a short "Select a player to load spotlight" prompt instead
    // of the verbose original. The test still guards that the empty state is
    // not blank.
    expect(screen.getByText(/select a player/i)).toBeInTheDocument()
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

    // Spotlight now renders the player name plus the model narrative as the
    // primary context strip; the verbose "Why this player matters now" /
    // "This player is available through cockpit context..." headings were
    // replaced with a tighter "no ranking row" hint when no ranking is
    // attached. Assertions track the current rendered copy.
    expect(screen.getByText("Scottie Scheffler")).toBeInTheDocument()
    expect(screen.getByText(spotlight.narrative!)).toBeInTheDocument()
    expect(
      screen.getByText(/no ranking row/i),
    ).toBeInTheDocument()
  })
})
