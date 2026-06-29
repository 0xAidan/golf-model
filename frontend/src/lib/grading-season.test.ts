import { describe, expect, it } from "vitest"

import {
  pickLatestGradedSeasonEvent,
  recentGradedSeasonEventsForTrend,
  sumUngradedPositiveEvForCompletedEvents,
} from "@/lib/grading-season"
import type { GradingSeasonEvent } from "@/lib/types"

const sampleEvents = [
  {
    event_id: "26",
    name: "U.S. Open",
    event_date: "2026-06-15",
    has_results: true,
    last_graded_at: "2026-06-22 02:00:00",
    lanes: {
      dashboard: {
        inventory_count: 100,
        graded_pick_count: 130,
        ungraded_positive_ev_count: 8,
        status: "partial",
        record: { wins: 0, losses: 0, pushes: 0, profit: 48, hit_rate: 0.4 },
        picks: [],
      },
      lab: {
        inventory_count: 0,
        graded_pick_count: 0,
        ungraded_positive_ev_count: 0,
        status: "no_data",
        record: { wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: 0 },
        picks: [],
      },
    },
  },
  {
    event_id: "34",
    name: "Travelers Championship",
    event_date: "2026-06-28",
    has_results: true,
    last_graded_at: "2026-06-29 18:03:16",
    lanes: {
      dashboard: {
        inventory_count: 100,
        graded_pick_count: 73,
        ungraded_positive_ev_count: 9,
        status: "partial",
        record: { wins: 40, losses: 31, pushes: 2, profit: 21.69, hit_rate: 0.548 },
        picks: [],
      },
      lab: {
        inventory_count: 0,
        graded_pick_count: 0,
        ungraded_positive_ev_count: 0,
        status: "no_data",
        record: { wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: 0 },
        picks: [],
      },
    },
  },
  {
    event_id: "30",
    name: "John Deere Classic",
    has_results: false,
    lanes: {
      dashboard: {
        inventory_count: 50,
        graded_pick_count: 0,
        ungraded_positive_ev_count: 7,
        status: "partial",
        record: { wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: 0 },
        picks: [],
      },
      lab: {
        inventory_count: 0,
        graded_pick_count: 0,
        ungraded_positive_ev_count: 0,
        status: "no_data",
        record: { wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: 0 },
        picks: [],
      },
    },
  },
] as unknown as GradingSeasonEvent[]

describe("grading-season helpers", () => {
  it("sums ungraded +EV only for events with results", () => {
    expect(sumUngradedPositiveEvForCompletedEvents(sampleEvents, "cockpit")).toBe(17)
  })

  it("picks latest graded event by last_graded_at", () => {
    expect(pickLatestGradedSeasonEvent(sampleEvents, "cockpit")?.event_id).toBe("34")
  })

  it("returns last graded events for trend chart", () => {
    const trend = recentGradedSeasonEventsForTrend(sampleEvents, "cockpit", 8)
    expect(trend.map((event) => event.event_id)).toEqual(["26", "34"])
  })
})
