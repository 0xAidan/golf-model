import { describe, expect, it } from "vitest"

import type { CompositePlayer, StandalonePlayerProfile } from "@/lib/types"

import { buildInsightSummary } from "./insight-summary"

describe("buildInsightSummary", () => {
  it("builds a sentence from model and skills", () => {
    const text = buildInsightSummary({
      modelPlayer: {
        player_key: "x",
        player_display: "X",
        rank: 3,
        composite: 71,
        form: 89,
        course_fit: 50,
        momentum: 1,
      } as CompositePlayer,
      standalone: {
        player_key: "x",
        player_display: "X",
        header: { player_display: "X" },
        sg_skills: { sg_app: 1.2, sg_total: 1 },
        approach_buckets: [],
        rolling_windows: {},
        trend_series: [],
        recent_events: [],
        has_skill_data: true,
        has_ranking_data: true,
        has_approach_data: false,
      } as StandalonePlayerProfile,
      fieldPercentiles: { form: 80 },
      linkedPicks: { matchups: [], secondary: [], totalCount: 2 },
    })
    expect(text).toContain("Model ranks #3")
    expect(text).toContain("2 +EV picks")
  })
})
