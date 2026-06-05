import { describe, expect, it } from "vitest"

import compositePlayersFixture from "@/__fixtures__/composite-players.json"
import gradingHistoryFixture from "@/__fixtures__/grading-history.json"
import teamEventSnapshotFixture from "@/__fixtures__/live-snapshot-team-event.json"

describe("frontend fixtures (snapshot contract)", () => {
  it("composite players fixture has stable field keys", () => {
    expect(compositePlayersFixture).toMatchInlineSnapshot(`
      [
        {
          "composite": 82.4,
          "course_fit": 78.5,
          "form": 80.1,
          "momentum_direction": "hot",
          "momentum_trend": 0.35,
          "player_display": "Player A",
          "player_key": "player_a",
          "rank": 1,
        },
        {
          "composite": 81.2,
          "course_fit": 77,
          "form": 79.4,
          "momentum_direction": "cold",
          "momentum_trend": -0.12,
          "player_display": "Player B",
          "player_key": "player_b",
          "rank": 2,
        },
      ]
    `)
  })

  it("grading history fixture exposes +EV summary picks", () => {
    expect(gradingHistoryFixture.summary?.combined?.picks).toBe(2)
    expect(gradingHistoryFixture.tournaments[0]?.picks?.every((p) => (p.ev ?? 0) > 0)).toBe(true)
  })

  it("team event snapshot fixture marks team format", () => {
    expect(teamEventSnapshotFixture.live_tournament?.event_format).toBe("team")
    expect(teamEventSnapshotFixture.live_tournament?.diagnostics?.state).toBe("team_event")
  })
})
