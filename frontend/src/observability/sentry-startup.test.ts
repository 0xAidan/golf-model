import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { prepareErrorReporting } from "@/observability/sentry-startup"

const { initSentry } = vi.hoisted(() => ({ initSentry: vi.fn() }))
vi.mock("@/observability/sentry", () => ({ initSentry }))

beforeEach(() => { initSentry.mockReset() })
afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("optional error reporting startup", () => {
  it("does not initialize reporting when no DSN is configured", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "")
    await prepareErrorReporting()
    expect(initSentry).not.toHaveBeenCalled()
  })

  it("finishes initialization before allowing configured app startup to continue", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://public@example.test/1")
    await prepareErrorReporting()
    expect(initSentry).toHaveBeenCalledOnce()
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
