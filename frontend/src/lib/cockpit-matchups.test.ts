import { describe, expect, it } from "vitest"

import { getMatchupStateMessage, hasActiveMatchupFilters } from "@/lib/cockpit-matchups"

describe("hasActiveMatchupFilters", () => {
  it("treats search text as an active filter", () => {
    expect(
      hasActiveMatchupFilters({
        selectedBooks: [],
        matchupSearch: "scheffler",
        minEdge: 0.02,
        defaultMinEdge: 0.02,
      }),
    ).toBe(true)
  })

  it("treats a raised min-edge threshold as an active filter", () => {
    expect(
      hasActiveMatchupFilters({
        selectedBooks: [],
        matchupSearch: "",
        minEdge: 0.08,
        defaultMinEdge: 0.02,
      }),
    ).toBe(true)
  })

  it("returns false when no user-controlled filters are active", () => {
    expect(
      hasActiveMatchupFilters({
        selectedBooks: [],
        matchupSearch: "",
        minEdge: 0.02,
        defaultMinEdge: 0.02,
      }),
    ).toBe(false)
  })
})

describe("getMatchupStateMessage", () => {
  it("prefers the filter-specific empty state when filters are active", () => {
    expect(
      getMatchupStateMessage({
        state: "market_available_no_edges",
        hasFilters: true,
      }),
    ).toBe("No matchup rows match current book/search/min-EV filters.")
  })
})
