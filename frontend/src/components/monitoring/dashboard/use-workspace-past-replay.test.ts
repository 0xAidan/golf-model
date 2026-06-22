import { describe, expect, it } from "vitest"

import { selectDefaultPastEvent } from "@/components/monitoring/dashboard/use-workspace-past-replay"

describe("selectDefaultPastEvent", () => {
  it("skips the current upcoming event id when choosing a default", () => {
    const options = [
      { event_id: "26", event_name: "U.S. Open", snapshot_count: 63 },
      { event_id: "32", event_name: "RBC Canadian Open", snapshot_count: 12 },
    ]

    const selected = selectDefaultPastEvent(options, "26")

    expect(selected?.event_id).toBe("32")
  })

  it("prefers events with graded picks when available", () => {
    const options = [
      { event_id: "32", event_name: "RBC Canadian Open", snapshot_count: 9 },
      { event_id: "26", event_name: "U.S. Open", snapshot_count: 346 },
    ]
    const gradingHistory = [
      { event_id: "26", name: "U.S. Open", graded_pick_count: 132, total_profit: 48.57 },
      { event_id: "32", name: "RBC Canadian Open", graded_pick_count: 0, total_profit: 0 },
    ]

    const selected = selectDefaultPastEvent(options, "32", gradingHistory)

    expect(selected?.event_id).toBe("26")
  })
})
