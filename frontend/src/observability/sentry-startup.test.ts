import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { prepareErrorReporting, startErrorReportingAfterPaint } from "@/observability/sentry-startup"

const { initSentry } = vi.hoisted(() => ({ initSentry: vi.fn() }))
vi.mock("@/observability/sentry", () => ({ initSentry }))

beforeEach(() => { initSentry.mockReset() })
afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("optional error reporting startup", () => {
  it("does not initialize reporting when no DSN is configured", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "")
    await prepareErrorReporting()
    expect(initSentry).not.toHaveBeenCalled()
  })

  it("initializes configured reporting independently of app startup", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://public@example.test/1")
    await prepareErrorReporting()
    expect(initSentry).toHaveBeenCalledOnce()
  })

  it("defers optional reporting until after a paint opportunity without blocking its caller", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://public@example.test/1")
    vi.useFakeTimers()
    let paint: FrameRequestCallback | undefined
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { paint = callback; return 1 })
    expect(startErrorReportingAfterPaint()).toBeUndefined()
    expect(initSentry).not.toHaveBeenCalled()
    paint?.(0)
    expect(initSentry).not.toHaveBeenCalled()
    await vi.runAllTimersAsync()
    await vi.dynamicImportSettled()
    expect(initSentry).toHaveBeenCalledOnce()
  })

  it("does not schedule a reporting download when no DSN is configured", () => {
    vi.stubEnv("VITE_SENTRY_DSN", "")
    const frame = vi.spyOn(window, "requestAnimationFrame")
    startErrorReportingAfterPaint()
    expect(frame).not.toHaveBeenCalled()
  })

  it("allows the app to render if optional error reporting initialization fails", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://public@example.test/1")
    const failure = new Error("Reporting unavailable")
    initSentry.mockImplementation(() => { throw failure })
    const log = vi.spyOn(console, "error").mockImplementation(() => {})
    await expect(prepareErrorReporting()).resolves.toBeUndefined()
    expect(log).toHaveBeenCalledWith("Error reporting could not initialize", failure)
  })
})
