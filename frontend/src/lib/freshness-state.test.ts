import { describe, expect, it } from "vitest"

import { deriveFreshnessState } from "@/lib/freshness-state"

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

  it("returns updating when fetching", () => {
    expect(
      deriveFreshnessState({
        isFetching: true,
        isOnline: true,
        isError: false,
        dataState: "fresh",
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
