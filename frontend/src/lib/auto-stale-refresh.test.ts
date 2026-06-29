import { describe, expect, it } from "vitest"

import { markAutoStaleRefresh, shouldAutoStaleRefresh, AUTO_STALE_REFRESH_COOLDOWN_MS } from "@/lib/auto-stale-refresh"

describe("auto-stale-refresh", () => {
  it("allows refresh when no prior timestamp", () => {
    sessionStorage.removeItem("golf-auto-refresh-at")
    expect(shouldAutoStaleRefresh()).toBe(true)
  })

  it("debounces within cooldown window", () => {
    markAutoStaleRefresh(1_000_000)
    expect(shouldAutoStaleRefresh(1_000_000 + AUTO_STALE_REFRESH_COOLDOWN_MS - 1)).toBe(false)
    expect(shouldAutoStaleRefresh(1_000_000 + AUTO_STALE_REFRESH_COOLDOWN_MS)).toBe(true)
  })
})
