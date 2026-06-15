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

  it("prefers events with snapshot history", () => {
    const options = [
      { event_id: "10", event_name: "Older Event", snapshot_count: 0 },
      { event_id: "32", event_name: "RBC Canadian Open", snapshot_count: 5 },
    ]

    const selected = selectDefaultPastEvent(options)

    expect(selected?.event_id).toBe("32")
  })
})
