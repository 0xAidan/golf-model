import { describe, expect, it } from "vitest"

import gradingHistoryFixture from "@/__fixtures__/grading-history.json"
import { buildGradingTrustMetrics } from "@/lib/grading-trust"
import type { GradingHistoryResponse } from "@/lib/types"

describe("buildGradingTrustMetrics", () => {
  it("uses summary +EV pick count from grading history fixture", () => {
    const metrics = buildGradingTrustMetrics(
      gradingHistoryFixture as GradingHistoryResponse,
      undefined,
    )

    expect(metrics.positiveEvPickCount).toBe(2)
    expect(metrics.lastGradedAt).toBe("2026-04-20T18:45:00Z")
  })

  it("shows ungraded banner when latest graded tournament has a pick gap", () => {
    const metrics = buildGradingTrustMetrics(undefined, {
      ai_status: { available: false },
      latest_graded_tournament: {
        name: "Pending Open",
        event_id: "600",
        picks_count: 3,
        graded_pick_count: 1,
      },
      latest_completed_event: {
        event_id: "600",
        event_name: "Pending Open",
        year: 2026,
      },
    })

    expect(metrics.ungradedPositiveEvCount).toBe(2)
    expect(metrics.showUngradedBanner).toBe(true)
  })

  it("flags completed event needing grade when ids differ", () => {
    const metrics = buildGradingTrustMetrics(undefined, {
      ai_status: { available: false },
      latest_graded_tournament: {
        name: "Old Open",
        event_id: "500",
        picks_count: 2,
        graded_pick_count: 2,
      },
      latest_completed_event: {
        event_id: "600",
        event_name: "New Open",
        year: 2026,
      },
    })

    expect(metrics.showUngradedBanner).toBe(true)
    expect(metrics.ungradedPositiveEvCount).toBeGreaterThan(0)
  })
})
