import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PastSecondaryGradeCell } from "@/components/monitoring/dashboard/workspace-grade-cells"
import type { FlattenedSecondaryBet } from "@/lib/types"

const baseBet: FlattenedSecondaryBet = {
  market: "outright",
  player: "Test Player",
  player_display: "Test Player",
  player_key: "test",
  odds: "+500",
  ev: 0.1,
}

describe("PastSecondaryGradeCell", () => {
  it("shows Ungraded not Pending when completed replay and no leaderboard", () => {
    render(
      <PastSecondaryGradeCell bet={baseBet} leaderboard={[]} completedReplay />,
    )
    expect(screen.getByText("Ungraded")).toBeInTheDocument()
  })

  it("shows W when graded_result is win", () => {
    render(
      <PastSecondaryGradeCell
        bet={{ ...baseBet, graded_result: "win" }}
        leaderboard={[]}
        completedReplay
      />,
    )
    expect(screen.getByText("W")).toBeInTheDocument()
  })
})
