import { describe, expect, test, vi } from "vitest"

import { getOperatorBoard } from "@/features/operator-data/operator-api"

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

  test("passes the TanStack signal to board fetches", async () => {
    const controller = new AbortController()
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
      expect.objectContaining({ signal: controller.signal }),
    )
  })
})
