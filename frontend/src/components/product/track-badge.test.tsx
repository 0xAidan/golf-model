import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TrackBadge } from "@/components/product/track-badge"

describe("TrackBadge", () => {
  it("labels the dashboard track as Champion with variant and short hash", () => {
    render(<TrackBadge track="dashboard" variant="baseline" configHash="011e7743e143e26b" />)
    const badge = screen.getByTestId("track-badge-dashboard")
    expect(badge).toHaveTextContent("Champion")
    expect(badge).toHaveTextContent("baseline")
    expect(screen.getByTestId("track-badge-hash-dashboard")).toHaveTextContent("#011e7743")
  })

  it("labels the lab track as Challenger", () => {
    render(<TrackBadge track="lab" variant="v5" configHash="3936389c4ef2d5b9" />)
    expect(screen.getByTestId("track-badge-lab")).toHaveTextContent("Challenger")
  })

  it("omits the hash chip when no config hash is provided", () => {
    render(<TrackBadge track="lab" variant="v5" />)
    expect(screen.queryByTestId("track-badge-hash-lab")).not.toBeInTheDocument()
  })
})
