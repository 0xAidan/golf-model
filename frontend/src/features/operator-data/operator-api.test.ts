import { afterEach, describe, expect, test, vi } from "vitest"

import { getOperatorBoard, getReadOnlyJson, requestRefreshNow } from "@/features/operator-data/operator-api"

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function pendingFetch(signal: AbortSignal): Promise<Response> {
  return new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true })
  })
}

describe("operator API", () => {
  test("parses structured API errors including retry metadata", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: { code: "snapshot_unavailable", message: "Snapshot unavailable", request_id: "req-42" },
          }),
          {
            status: 400,
            headers: { "content-type": "application/json", "retry-after": "7", "x-request-id": "req-header" },
          },
        ),
      ),
    )

    await expect(
      getOperatorBoard({ track: "champion", mode: "live", eventId: "event-1" }),
    ).rejects.toMatchObject({
      status: 400,
      code: "snapshot_unavailable",
      requestId: "req-42",
      retryAfterMs: 7_000,
      isTimeout: false,
    })
  })

  test("composes the TanStack signal and removes its listener after success", async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const add = vi.spyOn(controller.signal, "addEventListener")
    const remove = vi.spyOn(controller.signal, "removeEventListener")
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          schema_version: "operator-read-model/v1",
          track: "champion",
          mode: "live",
          state: "fresh",
          reason: { code: "ok", message: "Ready" },
          event: { event_id: "event-1" },
          source: {},
          eligibility: {},
          rankings: [],
          leaderboard: [],
          picks: { matchups: [], value_bets: [] },
        }),
        { status: 200, headers: { etag: '"board-1"' } },
      ),
    )
    vi.stubGlobal("fetch", fetchMock)

    await getOperatorBoard({ track: "champion", mode: "live", eventId: "event-1" }, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/operator/board?track=champion&mode=live&event_id=event-1",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    const requestSignal = fetchMock.mock.calls[0][1].signal as AbortSignal
    expect(requestSignal).not.toBe(controller.signal)
    expect(remove).toHaveBeenCalledWith("abort", add.mock.calls[0][1])
    controller.abort()
    expect(requestSignal.aborted).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  test("retains a ten-second timeout when an external signal is provided", async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const fetchMock = vi.fn((_url, init) => pendingFetch(init.signal))
    vi.stubGlobal("fetch", fetchMock)
    const request = getReadOnlyJson("/api/test", controller.signal)
    const result = expect(request).rejects.toMatchObject({ status: 0, code: "timeout", isTimeout: true })
    await vi.advanceTimersByTimeAsync(9_999)
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    await result
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(controller.signal.aborted).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  test("uses one overall deadline across the first request, retry delay, and retry", async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn((_url, init) => pendingFetch(init.signal))
    fetchMock.mockImplementationOnce(() => new Promise(resolve => {
      window.setTimeout(() => resolve(new Response("{}", { status: 503 })), 6_000)
    }))
    vi.stubGlobal("fetch", fetchMock)
    const result = expect(getReadOnlyJson("/api/test")).rejects.toMatchObject({ code: "timeout", isTimeout: true })
    await vi.advanceTimersByTimeAsync(6_250)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(3_750)
    await result
    expect(vi.getTimerCount()).toBe(0)
  })

  test.each([429, 500, 503])("retries a %s read only once", async status => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(() => Promise.resolve(new Response("{}", {
      status, headers: { "retry-after": "30" },
    })))
    vi.stubGlobal("fetch", fetchMock)
    const result = expect(getReadOnlyJson("/api/test")).rejects.toMatchObject({ status, retryAfterMs: 30_000 })
    await vi.advanceTimersByTimeAsync(999)
    expect(fetchMock).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(1)
    await result
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  test("retries a network failure once, but does not retry malformed JSON", async () => {
    vi.useFakeTimers()
    const networkError = new TypeError("Failed to fetch")
    const fetchMock = vi.fn().mockRejectedValue(networkError)
    vi.stubGlobal("fetch", fetchMock)
    const failed = expect(getReadOnlyJson("/api/test")).rejects.toBe(networkError)
    await vi.advanceTimersByTimeAsync(250)
    await failed
    expect(fetchMock).toHaveBeenCalledTimes(2)

    fetchMock.mockReset().mockResolvedValue(new Response("invalid JSON"))
    await expect(getReadOnlyJson("/api/test")).rejects.toBeInstanceOf(SyntaxError)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  test("caller abort during retry backoff cancels immediately and cleans timers/listeners", async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const remove = vi.spyOn(controller.signal, "removeEventListener")
    const fetchMock = vi.fn(() => Promise.resolve(new Response("{}", { status: 503 })))
    vi.stubGlobal("fetch", fetchMock)
    const request = getReadOnlyJson("/api/test", controller.signal)
    const result = expect(request).rejects.toMatchObject({ name: "AbortError" })
    await vi.advanceTimersByTimeAsync(100)
    controller.abort()
    await result
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
  })

  test("caller abort cancels an active read and a pre-aborted signal starts no request", async () => {
    vi.useFakeTimers()
    const controller = new AbortController()
    const fetchMock = vi.fn((_url, init) => pendingFetch(init.signal))
    vi.stubGlobal("fetch", fetchMock)
    const result = expect(getReadOnlyJson("/api/test", controller.signal)).rejects.toMatchObject({ name: "AbortError" })
    controller.abort()
    await result
    await expect(getReadOnlyJson("/api/test", controller.signal)).rejects.toBe(controller.signal.reason)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  test("never retries a mutation", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("{}", { status: 503 })))
    vi.stubGlobal("fetch", fetchMock)
    await expect(requestRefreshNow()).rejects.toMatchObject({ status: 503 })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]).toEqual(["/api/live-refresh/refresh", expect.objectContaining({ method: "POST" })])
  })
})
