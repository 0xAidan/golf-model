import { describe, expect, it } from "vitest"

import gradingHistoryFixture from "@/__fixtures__/grading-history.json"
import { buildGradingTrustMetrics } from "@/lib/grading-trust"
import type { GradingHistoryResponse, GradingSeasonResponse } from "@/lib/types"

const seasonWithUngraded = {
  year: 2026,
  lane: "dashboard",
  events: [
    {
      event_id: "30",
      name: "John Deere Classic",
      has_results: false,
      last_graded_at: null,
      lanes: {
        dashboard: {
          inventory_count: 100,
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
    {
      event_id: "34",
      name: "Travelers Championship",
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
  ],
  tournaments: [],
  summary: {
    dashboard: { picks: 73, wins: 40, losses: 31, pushes: 2, profit: 21.69, hit_rate: 0.548 },
    lab: { picks: 0, wins: 0, losses: 0, pushes: 0, profit: 0, hit_rate: 0 },
    comparison: {
      profit_delta: 0,
      hit_rate_delta: 0,
      picks_only_dashboard: 0,
      picks_only_lab: 0,
      overlap_matchups: 0,
    },
  },
} as unknown as GradingSeasonResponse

describe("buildGradingTrustMetrics", () => {
  it("uses summary +EV pick count from grading history fixture", () => {
    const metrics = buildGradingTrustMetrics(
      gradingHistoryFixture as GradingHistoryResponse,
      undefined,
    )

    expect(metrics.positiveEvPickCount).toBe(2)
    expect(metrics.lastGradedAt).toBe("2026-04-20T18:45:00Z")
    expect(metrics.autoGradeMessage).toBeNull()
  })

  it("counts ungraded +EV only for completed events with results", () => {
    const metrics = buildGradingTrustMetrics(undefined, undefined, undefined, seasonWithUngraded, "cockpit")

    expect(metrics.ungradedPositiveEvCount).toBe(9)
    expect(metrics.showUngradedBanner).toBe(true)
    expect(metrics.lastGradedAt).toBe("2026-06-29 18:03:16")
  })

  it("surfaces auto-grade awaiting-results message from live refresh status", () => {
    const metrics = buildGradingTrustMetrics(undefined, undefined, {
      last_auto_grade_status: {
        status: "captured",
        reason: "awaiting_results",
      },
    })

    expect(metrics.autoGradeMessage).toMatch(/waiting for Data Golf/i)
  })
})
