import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { renderHook } from "@testing-library/react"

import { useViewportTier } from "@/hooks/use-viewport"

function mockMatchMedia(matches: { mobile?: boolean; tablet?: boolean; desktop?: boolean }) {
  return vi.fn().mockImplementation((query: string) => ({
    matches:
      (query.includes("max-width: 767px") && matches.mobile) ||
      (query.includes("768px") && query.includes("1199px") && matches.tablet) ||
      (query.includes("min-width: 1200px") && matches.desktop) ||
      false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
}

describe("useViewportTier", () => {
  const originalMatchMedia = window.matchMedia

  beforeEach(() => {
    vi.stubGlobal("matchMedia", mockMatchMedia({ desktop: true }))
  })

  afterEach(() => {
    vi.stubGlobal("matchMedia", originalMatchMedia)
    vi.restoreAllMocks()
  })

  it("returns desktop when wide viewport matches", () => {
    const { result } = renderHook(() => useViewportTier())
    expect(result.current).toBe("desktop")
  })

  it("returns mobile when narrow viewport matches", () => {
    vi.stubGlobal("matchMedia", mockMatchMedia({ mobile: true }))
    const { result } = renderHook(() => useViewportTier())
    expect(result.current).toBe("mobile")
  })
})
