import { describe, expect, it } from "vitest"

import { mergeLabSnapshotSections } from "@/lib/lab-snapshot"
import type { LiveRefreshSnapshot } from "@/lib/types"

describe("mergeLabSnapshotSections", () => {
  it("returns null when lab keys are absent", () => {
    const snap: LiveRefreshSnapshot = {
      live_tournament: { event_name: "A" } as LiveRefreshSnapshot["live_tournament"],
    }
    expect(mergeLabSnapshotSections(snap)).toBeNull()
  })

  it("merges lab sections over prod keys when present", () => {
    const snap: LiveRefreshSnapshot = {
      live_tournament: { event_name: "Prod live" } as LiveRefreshSnapshot["live_tournament"],
      upcoming_tournament: { event_name: "Prod up" } as LiveRefreshSnapshot["upcoming_tournament"],
      lab_live_tournament: { event_name: "Lab live" } as LiveRefreshSnapshot["live_tournament"],
      lab_upcoming_tournament: { event_name: "Lab up" } as LiveRefreshSnapshot["upcoming_tournament"],
    }
    const merged = mergeLabSnapshotSections(snap)
    expect(merged?.live_tournament?.event_name).toBe("Lab live")
    expect(merged?.upcoming_tournament?.event_name).toBe("Lab up")
  })

  it("returns null when both lab sections are JSON null", () => {
    const snap: LiveRefreshSnapshot = {
      lab_live_tournament: null,
      lab_upcoming_tournament: null,
    }
    expect(mergeLabSnapshotSections(snap)).toBeNull()
  })
})
