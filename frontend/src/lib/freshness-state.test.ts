import { describe, expect, it } from "vitest"

import { deriveFreshnessState, freshnessLabel } from "@/lib/freshness-state"

describe("deriveFreshnessState", () => {
  it("returns offline when navigator offline", () => {
    expect(
      deriveFreshnessState({
        isFetching: false,
        isOnline: false,
        isError: false,
      }),
    ).toBe("offline")
  })

  it("returns updating when fetching without usable display data", () => {
    expect(
      deriveFreshnessState({
        isFetching: true,
        isOnline: true,
        isError: false,
        dataState: "fresh",
        hasDisplayData: false,
      }),
    ).toBe("updating")
  })

  it("stays fresh during background poll when display data exists", () => {
    expect(
      deriveFreshnessState({
        isFetching: true,
        isOnline: true,
        isError: false,
        dataState: "fresh",
        hasDisplayData: true,
      }),
    ).toBe("fresh")
  })

  it("returns updating when refresh is queued even with display data", () => {
    expect(
      deriveFreshnessState({
        isFetching: false,
        refreshQueued: true,
        isOnline: true,
        isError: false,
        dataState: "stale",
        hasDisplayData: true,
      }),
    ).toBe("updating")
  })

  it("returns updating when refresh is queued", () => {
    expect(
      deriveFreshnessState({
        isFetching: false,
        refreshQueued: true,
        isOnline: true,
        isError: false,
        dataState: "stale",
      }),
    ).toBe("updating")
  })

  it("returns stale when data_state stale", () => {
    expect(
      deriveFreshnessState({
        isFetching: false,
        isOnline: true,
        isError: false,
        dataState: "stale",
      }),
    ).toBe("stale")
  })
})

describe("freshnessLabel", () => {
  it("does not claim refreshing for idle stale state", () => {
    const label = freshnessLabel("stale", 7200, () => "stale (>60m)")
    expect(label).toBe("Stale · stale (>60m)")
    expect(label.toLowerCase()).not.toContain("refreshing")
  })
})
