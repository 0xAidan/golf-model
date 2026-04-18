import { describe, expect, it } from "vitest"

import { mergeTrackRecordEvents } from "@/lib/track-record"
import type { TrackRecordEvent } from "@/lib/types"

describe("mergeTrackRecordEvents", () => {
  it("falls back to static picks when the API event has none", () => {
    const apiEvents: TrackRecordEvent[] = [
      {
        id: 1,
        name: "Valspar Championship",
        course: "Innisbrook Resort (Copperhead)",
        graded_pick_count: 0,
        hits: 9,
        wins: 9,
        pushes: 3,
        losses: 4,
        total_profit: 3.41,
        picks: [],
      },
    ]

    const staticEvents = [
      {
        name: "Valspar Championship",
        course: "Innisbrook Resort (Copperhead)",
        record: { wins: 9, losses: 4, pushes: 3 },
        profit_units: 3.41,
        picks: [
          { pick: "Player A", opponent: "Player B", odds: "+100", result: "win", pl: 1 },
        ],
      },
    ]

    const result = mergeTrackRecordEvents(apiEvents, staticEvents)

    expect(result.events).toHaveLength(1)
    expect(result.events[0]?.picks).toEqual(staticEvents[0]?.picks)
    expect(result.totals).toEqual({
      wins: 9,
      losses: 4,
      pushes: 3,
      profit: 3.41,
    })
  })

  it("keeps API picks when they exist and appends static-only events", () => {
    const apiEvents: TrackRecordEvent[] = [
      {
        id: 2,
        name: "Genesis Invitational",
        course: "Riviera Country Club",
        graded_pick_count: 1,
        hits: 1,
        wins: 1,
        pushes: 0,
        losses: 0,
        total_profit: 1.15,
        picks: [
          {
            player_display: "Player C",
            opponent_display: "Player D",
            market_odds: "-115",
            hit: 1,
            profit: 1.15,
          },
        ],
      },
    ]

    const staticEvents = [
      {
        name: "Genesis Invitational",
        course: "Riviera Country Club",
        record: { wins: 5, losses: 2, pushes: 1 },
        profit_units: 2.64,
        picks: [
          { pick: "Static Pick", opponent: "Static Opponent", odds: "+100", result: "win", pl: 1 },
        ],
      },
      {
        name: "Static Only Event",
        course: "Static Course",
        record: { wins: 2, losses: 1, pushes: 0 },
        profit_units: 0.8,
        picks: [],
      },
    ]

    const result = mergeTrackRecordEvents(apiEvents, staticEvents)

    expect(result.events).toHaveLength(2)
    expect(result.events[0]?.picks).toEqual([
      { pick: "Player C", opponent: "Player D", odds: "-115", result: "win", pl: 1.15 },
    ])
    expect(result.events[1]?.name).toBe("Static Only Event")
    expect(result.totals).toEqual({
      wins: 3,
      losses: 1,
      pushes: 0,
      profit: 1.95,
    })
  })
})
