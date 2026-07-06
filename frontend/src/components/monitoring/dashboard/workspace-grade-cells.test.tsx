import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  PastPickGradeCell,
  PastSecondaryGradeCell,
} from "@/components/monitoring/dashboard/workspace-grade-cells"
import type { FlattenedSecondaryBet, MatchupBet } from "@/lib/types"

const baseBet: FlattenedSecondaryBet = {
  market: "outright",
  player: "Test Player",
  player_display: "Test Player",
  player_key: "test",
  odds: "+500",
  ev: 0.1,
}

const baseMatchup: MatchupBet = {
  pick: "Test Player",
  pick_key: "test-player",
  opponent: "Other Player",
  opponent_key: "other-player",
  odds: "+110",
  ev: 0.08,
  ev_pct: "8.0%",
  model_win_prob: 0.54,
  implied_prob: 0.46,
  composite_gap: 0.7,
  form_gap: 0.2,
  course_fit_gap: 0.1,
  reason: "Test reason",
}

describe("PastSecondaryGradeCell", () => {
  it("shows Ungraded not Pending when completed replay and no leaderboard", () => {
    render(
      <PastSecondaryGradeCell bet={baseBet} leaderboard={[]} completedReplay />,
    )
    expect(screen.getByText("Ungraded")).toBeInTheDocument()
  })

  it("shows Awaiting results before the event finishes", () => {
    render(
      <PastSecondaryGradeCell bet={baseBet} leaderboard={[]} />,
    )
    expect(screen.getByText("Awaiting results")).toBeInTheDocument()
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

  it("prefers stored graded_result over leaderboard inference", () => {
    render(
      <PastSecondaryGradeCell
        bet={{ ...baseBet, graded_result: "loss" }}
        leaderboard={[{ player: "Test Player", position: "1", rank: 1, player_key: "test" }]}
        completedReplay
      />,
    )
    expect(screen.getByText("L")).toBeInTheDocument()
  })
})

describe("PastPickGradeCell", () => {
  it("shows Awaiting results instead of Pending before completion", () => {
    render(
      <PastPickGradeCell matchup={baseMatchup} leaderboard={[]} />,
    )
    expect(screen.getByText("Awaiting results")).toBeInTheDocument()
  })
})
