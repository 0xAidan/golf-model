import { describe, expect, it } from "vitest"

import {
  gradeTournamentMatchupFromLeaderboard,
  readStoredMatchupOutcome,
  resolvePastMatchupGrade,
} from "@/lib/matchup-pick-grade"
import type { LiveLeaderboardRow, MatchupBet } from "@/lib/types"

const baseMatchup = (over: Partial<MatchupBet> = {}): MatchupBet => ({
  pick: "A",
  pick_key: "player_a",
  opponent: "B",
  opponent_key: "player_b",
  odds: "-110",
  model_win_prob: 0.55,
  implied_prob: 0.52,
  ev: 0.03,
  ev_pct: "3.0%",
  composite_gap: 0,
  form_gap: 0,
  course_fit_gap: 0,
  reason: "test",
  ...over,
})

function lb(
  key: string,
  name: string,
  finish: string | undefined,
  over: Partial<LiveLeaderboardRow> = {},
): LiveLeaderboardRow {
  return {
    rank: 1,
    player_key: key,
    player: name,
    finish_state: finish,
    ...over,
  }
}

describe("matchup-pick-grade", () => {
  it("grades win when pick finishes ahead", () => {
    const board = [lb("player_a", "A", "3"), lb("player_b", "B", "12")]
    expect(gradeTournamentMatchupFromLeaderboard(baseMatchup(), board)).toBe("win")
    const g = resolvePastMatchupGrade(baseMatchup(), board)
    expect(g.kind).toBe("letter")
    if (g.kind === "letter") expect(g.letter).toBe("W")
  })

  it("grades loss when opponent finishes ahead", () => {
    const board = [lb("player_a", "A", "20"), lb("player_b", "B", "5")]
    expect(gradeTournamentMatchupFromLeaderboard(baseMatchup(), board)).toBe("loss")
    const g = resolvePastMatchupGrade(baseMatchup(), board)
    expect(g.kind).toBe("letter")
    if (g.kind === "letter") expect(g.letter).toBe("L")
  })

  it("grades push on same finish rank", () => {
    const board = [lb("player_a", "A", "T8"), lb("player_b", "B", "T8")]
    expect(gradeTournamentMatchupFromLeaderboard(baseMatchup(), board)).toBe("push")
    const g = resolvePastMatchupGrade(baseMatchup(), board)
    expect(g.kind).toBe("letter")
    if (g.kind === "letter") expect(g.letter).toBe("P")
  })

  it("returns pending when a player is missing from the leaderboard", () => {
    const board = [lb("player_a", "A", "5")]
    expect(gradeTournamentMatchupFromLeaderboard(baseMatchup(), board)).toBe(null)
    expect(resolvePastMatchupGrade(baseMatchup(), board).kind).toBe("pending")
  })

  it("uses position when finish_state is absent", () => {
    const board: LiveLeaderboardRow[] = [
      { rank: 1, player_key: "player_a", player: "A", position: "2" },
      { rank: 2, player_key: "player_b", player: "B", position: "15" },
    ]
    expect(gradeTournamentMatchupFromLeaderboard(baseMatchup(), board)).toBe("win")
  })

  it("does not grade round_matchups from leaderboard", () => {
    const board = [lb("player_a", "A", "3"), lb("player_b", "B", "30")]
    const m = baseMatchup({ market_type: "round_matchups" })
    expect(gradeTournamentMatchupFromLeaderboard(m, board)).toBe(null)
    expect(resolvePastMatchupGrade(m, board).kind).toBe("dash")
  })

  it("reads explicit stored outcomes without inferring loss from hit=0", () => {
    expect(readStoredMatchupOutcome({ outcome: "loss" })).toBe("loss")
    expect(readStoredMatchupOutcome({ hit: 0 })).toBe(null)
    expect(readStoredMatchupOutcome({ hit: 1 })).toBe("win")
    expect(readStoredMatchupOutcome({ is_push: true })).toBe("push")
  })

  it("returns ungraded on completed replay when leaderboard is incomplete", () => {
    const board = [lb("player_a", "A", "5")]
    expect(resolvePastMatchupGrade(baseMatchup(), board, { completedReplay: true }).kind).toBe("ungraded")
  })

  it("prefers graded_result on the matchup over leaderboard", () => {
    const board = [lb("player_a", "A", "50"), lb("player_b", "B", "1")]
    const m = baseMatchup({ graded_result: "win" })
    const g = resolvePastMatchupGrade(m, board)
    expect(g.kind).toBe("letter")
    if (g.kind === "letter") expect(g.letter).toBe("W")
  })

  it("resolves grades when stored keys differ from leaderboard ids but names match", () => {
    const board = [lb("dg_patrick", "Patrick Rodgers", "T10"), lb("dg_sung", "Sungjae Im", "T22")]
    const m = baseMatchup({
      pick_key: "wrong_pick_key",
      opponent_key: "wrong_opp_key",
      pick: "Patrick Rodgers",
      opponent: "Sungjae Im",
    })
    expect(gradeTournamentMatchupFromLeaderboard(m, board)).toBe("win")
  })
})
