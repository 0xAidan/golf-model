import { describe, expect, test } from "vitest"

import { getPreviewViewState } from "@/features/operator-data/view-state"

describe("preview view state", () => {
  test("uses stale state when only a last-good board is available", () => {
    expect(
      getPreviewViewState({
        bootstrap: undefined,
        board: undefined,
        hasLastGood: true,
        cacheHydrationPending: false,
        isBoardLoading: false,
        isBoardError: true,
      }),
    ).toBe("stale")
  })

  test("does not treat split-brain bootstrap data as current", () => {
    expect(
      getPreviewViewState({
        bootstrap: {
          schema_version: "operator-read-model/v1",
          state: "error",
          reason: { code: "split_brain", message: "Path mismatch" },
          source: {},
          tracks: {
            champion: {} as never,
            challenger: {} as never,
          },
        },
        board: undefined,
        hasLastGood: false,
        cacheHydrationPending: false,
        isBoardLoading: false,
        isBoardError: false,
      }),
    ).toBe("error")
  })
})
