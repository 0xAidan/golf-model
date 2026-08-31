import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PlayerFace, playerInitials } from "@/components/ui/player-face"

describe("PlayerFace", () => {
  it("builds two-letter initials", () => {
    expect(playerInitials("Scottie Scheffler")).toBe("SS")
    expect(playerInitials("")).toBe("?")
  })

  it("shows initials when no player key is provided", () => {
    render(<PlayerFace name="Rory McIlroy" />)
    expect(screen.getByText("RM")).toBeInTheDocument()
    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })

  it("renders a local photo URL when a key is present and eager", () => {
    render(<PlayerFace playerKey="rory_mcilroy" name="Rory McIlroy" eager />)
    expect(screen.getByTestId("player-face-img")).toHaveAttribute(
      "src",
      "/api/players/rory_mcilroy/photo",
    )
  })

  it("shows a country code beside the face", () => {
    render(<PlayerFace name="Ludvig Aberg" country="SWE" />)
    expect(screen.getByTestId("player-face-country")).toHaveTextContent("SWE")
  })
})
