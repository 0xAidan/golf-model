import { describe, expect, it } from "vitest"

import {
  buildLiveRankingsColumns,
  buildUpcomingRankingsColumns,
} from "@/lib/cockpit-columns"

const noop = () => {}

describe("rankings column builders", () => {
  it("upcoming columns are model-centric without live scoring headers", () => {
    const cols = buildUpcomingRankingsColumns({
      onPlayerSelect: noop,
      trajectoryBounds: { min: -2, max: 2 },
    })
    const headers = cols.map((c) => (typeof c.header === "string" ? c.header : c.id))
    expect(headers).toContain("#")
    expect(headers).toContain("Composite")
    expect(headers).toContain("Form")
    expect(headers).toContain("Course")
    expect(headers).toContain("Mom.")
    expect(headers).toContain("SG Traj")
    expect(headers).not.toContain("Model now")
    expect(headers).not.toContain("Model Δ")
    expect(headers).not.toContain("Pos Δ")
    expect(headers).not.toContain("To par")
  })

  it("live columns include model rank movement inline and scoring columns", () => {
    const cols = buildLiveRankingsColumns({
      onPlayerSelect: noop,
      trajectoryBounds: { min: -2, max: 2 },
    })
    const headers = cols.map((c) => (typeof c.header === "string" ? c.header : c.id))
    expect(headers).toContain("Model now")
    expect(headers).not.toContain("Start (model)")
    expect(headers).not.toContain("Model Δ")
    expect(headers).toContain("Pos")
    expect(headers).not.toContain("Start pos")
    expect(headers).toContain("Pos Δ")
    expect(headers).toContain("To par")
    expect(headers).toContain("SG Traj")
    expect(headers).toContain("Composite")
    expect(headers).not.toContain("Form")
  })
})
