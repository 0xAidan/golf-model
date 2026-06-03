import { describe, expect, it } from "vitest"

import {
  buildExplorableMatchupPool,
  failedCandidateToMatchupBet,
  filterMatchupsForExploration,
} from "./matchup-edge-filter"
import type { FailedMatchupCandidate, MatchupBet } from "./types"

const cardRow = (overrides: Partial<MatchupBet> = {}): MatchupBet => ({
  pick: "Player A",
  pick_key: "player_a",
  opponent: "Player B",
  opponent_key: "player_b",
  odds: "-110",
  book: "draftkings",
  model_win_prob: 0.55,
  implied_prob: 0.5,
  ev: 0.06,
  ev_pct: "6.0%",
  composite_gap: 1,
  form_gap: 0,
  course_fit_gap: 0,
  reason: "Card pick",
  ...overrides,
})

const failedRow = (overrides: Partial<FailedMatchupCandidate> = {}): FailedMatchupCandidate => ({
  pick: "Player C",
  opponent: "Player D",
  book: "fanduel",
  odds: -105,
  ev: 0.038,
  reason_code: "below_ev_threshold",
  ...overrides,
})

describe("matchup-edge-filter", () => {
  it("merges card rows with failed candidates without duplicates", () => {
    const pool = buildExplorableMatchupPool([cardRow()], [failedRow()])
    expect(pool).toHaveLength(2)
  })

  it("prefers card row when the same matchup key exists in both pools", () => {
    const pool = buildExplorableMatchupPool(
      [cardRow({ ev: 0.06 })],
      [failedRow({ pick: "Player A", opponent: "Player B", book: "draftkings", ev: 0.03 })],
    )
    expect(pool).toHaveLength(1)
    expect(pool[0]?.ev).toBe(0.06)
    expect(pool[0]?.explore_source).toBe("card")
  })

  it("filters dynamically by min edge and sorts by EV descending", () => {
    const filtered = filterMatchupsForExploration(
      [cardRow({ ev: 0.06 })],
      [failedRow({ ev: 0.038 }), failedRow({ pick: "X", opponent: "Y", book: "betmgm", ev: 0.02 })],
      { selectedBooks: [], matchupSearch: "", minEdge: 0.03 },
    )
    expect(filtered.map((row) => row.ev)).toEqual([0.06, 0.038])
  })

  it("skips failed candidates without numeric EV", () => {
    expect(
      failedCandidateToMatchupBet(
        failedRow({ ev: null, reason_code: "dg_model_disagreement" }),
      ),
    ).toBeNull()
  })
})
