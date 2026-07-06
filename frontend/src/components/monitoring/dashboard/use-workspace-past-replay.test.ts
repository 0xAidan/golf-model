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

  it("prefers the most recent graded event in API order, not highest graded count", () => {
    const options = [
      { event_id: "34", event_name: "Travelers Championship", snapshot_count: 527 },
      { event_id: "26", event_name: "U.S. Open", snapshot_count: 346 },
    ]
    const gradingHistory = [
      { event_id: "34", name: "Travelers Championship", graded_pick_count: 73, total_profit: 47.82 },
      { event_id: "26", name: "U.S. Open", graded_pick_count: 130, total_profit: 48.57 },
    ]

    const selected = selectDefaultPastEvent(options, undefined, gradingHistory)

    expect(selected?.event_id).toBe("34")
  })

  it("uses preferred latest-completed event id when provided", () => {
    const options = [
      { event_id: "34", event_name: "Travelers Championship", snapshot_count: 527 },
      { event_id: "26", event_name: "U.S. Open", snapshot_count: 346 },
    ]
    const gradingHistory = [
      { event_id: "26", name: "U.S. Open", graded_pick_count: 130, total_profit: 48.57 },
    ]

    const selected = selectDefaultPastEvent(options, undefined, gradingHistory, "34")

    expect(selected?.event_id).toBe("34")
  })

  it("falls back to the first event with snapshots when no graded history exists", () => {
    const options = [
      { event_id: "41", event_name: "Genesis Scottish Open", snapshot_count: 0 },
      { event_id: "40", event_name: "Rocket Classic", snapshot_count: 12 },
      { event_id: "39", event_name: "RBC Canadian Open", snapshot_count: 4 },
    ]

    const selected = selectDefaultPastEvent(options)

    expect(selected?.event_id).toBe("40")
  })
})
