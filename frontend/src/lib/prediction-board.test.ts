import { describe, expect, it } from "vitest"

import { buildHydratedPredictionRun } from "@/lib/prediction-board"
import type { LiveRefreshSnapshot } from "@/lib/types"

describe("buildHydratedPredictionRun", () => {
  it("preserves enriched ranking fields from snapshot rows", () => {
    const snapshot: LiveRefreshSnapshot = {
      live_tournament: {
        event_name: "Masters Tournament",
        course_name: "Augusta National",
        field_size: 88,
        tournament_id: 9,
        course_num: 10,
        rankings: [
          {
            rank: 1,
            player_key: "jon_rahm",
            player: "Jon Rahm",
            composite: 84.5,
            course_fit: 81.2,
            form: 83.7,
            momentum: 79.1,
            momentum_direction: "hot",
            course_confidence: 0.82,
            course_rounds: 26,
            weather_adjustment: 0.6,
            availability: { status: "fit" },
            form_flags: ["recent_withdrawal_risk"],
            form_notes: ["Back in field this week."],
            details: {
              course_components: { driving: 1.2 },
              form_components: { consistency: 0.9 },
              momentum_windows: { w12: 0.4 },
            },
          },
        ],
        matchup_bets: [],
        value_bets: {},
      },
    }

    const run = buildHydratedPredictionRun(snapshot, "live")
    expect(run).not.toBeNull()
    expect(run?.composite_results).toHaveLength(1)
    const player = run?.composite_results?.[0]
    expect(player?.availability).toEqual({ status: "fit" })
    expect(player?.form_flags).toEqual(["recent_withdrawal_risk"])
    expect(player?.form_notes).toEqual(["Back in field this week."])
    expect(player?.details?.course_components?.driving).toBe(1.2)
  })

  it("returns empty rankings and warning when eligibility fails", () => {
    const snapshot: LiveRefreshSnapshot = {
      live_tournament: {
        event_name: "Masters Tournament",
        course_name: "Augusta National",
        eligibility: {
          verified: false,
          summary: "Field verification failed.",
          action: "Retry after field updates.",
        },
      },
    }

    const run = buildHydratedPredictionRun(snapshot, "live")
    expect(run).not.toBeNull()
    expect(run?.composite_results).toEqual([])
    expect(run?.warnings?.[0]).toContain("Field verification failed.")
  })
})
