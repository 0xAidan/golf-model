import { describe, expect, it } from "vitest"

import {
  getCurrentRelease,
  shouldHardReloadForChunkError,
} from "@/lib/lazy-import"

describe("chunk recovery", () => {
  it("hard reloads a chunk failure only once per release", () => {
    const storage = new Map<string, string>()
    const reload = () => undefined

    expect(
      shouldHardReloadForChunkError({
        error: new Error("Failed to fetch dynamically imported module"),
        release: "release-123",
        storage,
        reload,
      }),
    ).toBe(true)
    expect(
      shouldHardReloadForChunkError({
        error: new Error("Failed to fetch dynamically imported module"),
        release: "release-123",
        storage,
        reload,
      }),
    ).toBe(false)
  })

  it("does not reload for a normal route error", () => {
    expect(
      shouldHardReloadForChunkError({
        error: new Error("Route data was invalid"),
        release: getCurrentRelease(),
        storage: new Map<string, string>(),
        reload: () => undefined,
      }),
    ).toBe(false)
  })
})
