import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { usePredictionTab } from "@/hooks/use-prediction-tab"

describe("usePredictionTab", () => {
  it("switches to live when live data arrives and the user has not changed modes", async () => {
    const { result, rerender } = renderHook(
      ({ isLiveActive }) => usePredictionTab(isLiveActive),
      { initialProps: { isLiveActive: false } },
    )

    expect(result.current.predictionTab).toBe("upcoming")

    rerender({ isLiveActive: true })

    await waitFor(() => {
      expect(result.current.predictionTab).toBe("live")
    })
  })

  it("does not clobber an intentional user selection when live data arrives later", async () => {
    const { result, rerender } = renderHook(
      ({ isLiveActive }) => usePredictionTab(isLiveActive),
      { initialProps: { isLiveActive: false } },
    )

    act(() => {
      result.current.setPredictionTab("past")
    })

    rerender({ isLiveActive: true })

    await waitFor(() => {
      expect(result.current.predictionTab).toBe("past")
    })
  })

  it("respects an intentional user change even during a live event", async () => {
    const { result, rerender } = renderHook(
      ({ isLiveActive }) => usePredictionTab(isLiveActive),
      { initialProps: { isLiveActive: true } },
    )

    expect(result.current.predictionTab).toBe("live")

    act(() => {
      result.current.setPredictionTab("upcoming")
    })

    rerender({ isLiveActive: true })

    await waitFor(() => {
      expect(result.current.predictionTab).toBe("upcoming")
    })
  })
})
